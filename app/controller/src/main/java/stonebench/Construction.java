package stonebench;

import com.google.gson.*;
import java.util.*;
import net.minecraft.block.*;
import net.minecraft.inventory.Inventory;
import net.minecraft.item.*;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.Hand;
import net.minecraft.util.hit.BlockHitResult;
import net.minecraft.util.math.*;

/** Validate using a read-only view of the final geometry, then publish once. */
public final class Construction {
    record Placement(BlockPos pos,BlockCatalog.Entry entry,JsonObject parameters,List<ItemStack> inventory,BlockState state) {}
    private static Map<BlockPos,BlockState> preview;
    private static BlockPos placementPosition;
    static boolean failNextLot;
    private static boolean installing; private static int deferredComparators;
    public static boolean deferComparatorUpdate() {if(!installing) return false;deferredComparators++;return true;}
    private static ServerWorld observedWorld; private static List<Placement> observedPlacements; private static JsonArray events; private static int rootIndex=-1;
    public static void observe(String kind,BlockPos pos) {
        if(events==null) return; boolean geometry=true,inventories=true,parameters=true;
        for(Placement p:observedPlacements) {
            BlockState actual=observedWorld.getBlockState(p.pos);geometry &= actual.isOf(p.state.getBlock());
            for(var pair:p.state.getEntries().entrySet()) if(p.entry.parameters().contains(pair.getKey().getName())) parameters &= pair.getValue().equals(actual.getEntries().get(pair.getKey()));
            if(p.inventory!=null) { if(!(observedWorld.getBlockEntity(p.pos) instanceof Inventory inv)) inventories=false; else for(int slot=0;slot<p.inventory.size();slot++) inventories &= ItemStack.areEqual(inv.getStack(slot),p.inventory.get(slot)); }
        }
        JsonObject event=new JsonObject();event.addProperty("kind",kind);event.add("position",Task.position(pos.getX(),pos.getY(),pos.getZ()));event.addProperty("root_index",rootIndex);event.addProperty("geometry_complete",geometry);event.addProperty("inventories_complete",inventories);event.addProperty("parameters_complete",parameters);events.add(event);
    }
    public static BlockState previewState(BlockPos pos) {return preview==null?null:pos.equals(placementPosition)?Blocks.AIR.getDefaultState():preview.get(pos);}
    static List<Placement> validate(ServerWorld world,JsonObject args) {
        JsonElement raw=args.get("blocks");if(raw==null || !raw.isJsonArray() || raw.getAsJsonArray().size()<1 || raw.getAsJsonArray().size()>256) throw new IllegalArgumentException("blocks must contain 1..256 ordered placements");
        if(!args.has("notify_neighbors") || !args.get("notify_neighbors").isJsonPrimitive() || !args.get("notify_neighbors").getAsJsonPrimitive().isBoolean()) throw new IllegalArgumentException("notify_neighbors must be an explicit boolean");
        List<Placement> placements=new ArrayList<>();Map<BlockPos,BlockState> overlay=new LinkedHashMap<>();
        for(JsonElement value:raw.getAsJsonArray()) {
            if(!value.isJsonObject()) throw new IllegalArgumentException("Each placement must be an object");JsonObject row=value.getAsJsonObject();
            if(!Set.of("x","y","z","block","parameters","inventory").containsAll(row.keySet())) throw new IllegalArgumentException("Unexpected placement field; raw state/NBT is forbidden");
            BlockPos pos=new BlockPos(Task.integer(row,"x",-30000000,30000000),Task.integer(row,"y",world.getBottomY(),world.getTopYInclusive()),Task.integer(row,"z",-30000000,30000000));
            if(!world.isInBuildLimit(pos) || !world.getWorldBorder().contains(pos)) throw new IllegalArgumentException("Position outside vanilla build limits/world border");
            if(overlay.containsKey(pos)) throw new IllegalArgumentException("Duplicate placement coordinate");
            BlockCatalog.Entry entry=BlockCatalog.entry(Task.string(row,"block"));
            if(row.has("parameters")&&!row.get("parameters").isJsonObject()) throw new IllegalArgumentException("parameters must be an object");
            JsonObject parameters=row.has("parameters")?row.getAsJsonObject("parameters"):new JsonObject();
            BlockState state=BlockCatalog.parameters(entry.block().getDefaultState(),parameters,entry);
            List<ItemStack> inventory=BlockCatalog.inventory(row.get("inventory"),entry,pos,state,world);
            overlay.put(pos,state);placements.add(new Placement(pos,entry,parameters,inventory,state));
        }
        preview=overlay;
        try {
            List<Placement> resolved=new ArrayList<>();
            for(Placement placement:placements) {
                BlockPos pos=placement.pos;String face=placement.parameters.has("face")?placement.parameters.get("face").getAsString():"floor";
                Direction facing=placement.parameters.has("facing")?Direction.byId(placement.parameters.get("facing").getAsString()):Direction.NORTH;
                Direction side=face.equals("ceiling")?Direction.DOWN:face.equals("wall")?facing:Direction.UP;
                ItemPlacementContext context=new ItemPlacementContext(world,null,Hand.MAIN_HAND,new ItemStack(placement.entry.block().asItem()),new BlockHitResult(Vec3d.ofCenter(pos),side,pos.offset(side.getOpposite()),false)) {
                    @Override public BlockPos getBlockPos() {return pos;}
                    @Override public boolean canReplaceExisting() {return false;}
                    @Override public Direction getHorizontalPlayerFacing() {return facing.getAxis().isHorizontal()?facing.getOpposite():Direction.SOUTH;}
                    @Override public Direction getPlayerLookDirection() {return facing.getOpposite();}
                    @Override public Direction getVerticalPlayerLookDirection() {return facing==Direction.UP?Direction.DOWN:Direction.UP;}
                    @Override public float getPlayerYaw() {return getHorizontalPlayerFacing().getPositiveHorizontalDegrees();}
                    @Override public Direction[] getPlacementDirections() {return new Direction[]{side.getOpposite(),Direction.DOWN,Direction.NORTH,Direction.SOUTH,Direction.WEST,Direction.EAST,Direction.UP};}
                };
                placementPosition=pos;BlockState state;
                try {state=placement.entry.block().getPlacementState(context);} finally {placementPosition=null;}
                if(state==null) throw new IllegalArgumentException("No vanilla placement state at "+pos);
                state=BlockCatalog.parameters(state,placement.parameters,placement.entry);
                if(!state.canPlaceAt(world,pos)) throw new IllegalArgumentException("Vanilla placement lacks support at "+pos);
                resolved.add(new Placement(pos,placement.entry,placement.parameters,placement.inventory,state));
            }
            return resolved;
        } finally {preview=null;placementPosition=null;}
    }
    static JsonArray read(ServerWorld world,List<Placement> placements) {JsonArray result=new JsonArray();for(Placement p:placements) result.add(BlockCatalog.read(world,p.pos));return result;}
    static JsonObject apply(ServerWorld world,List<Placement> placements,boolean notify) {
        if(Controller.TEST) {observedWorld=world;observedPlacements=placements;events=new JsonArray();}
        try {
        installing=true;deferredComparators=0;
        List<BlockState> old=new ArrayList<>();for(Placement p:placements) old.add(world.getBlockState(p.pos));
        for(Placement p:placements) {
            boolean changed=world.setBlockState(p.pos,p.state,Block.FORCE_STATE_AND_SKIP_CALLBACKS_AND_DROPS);
            if(!changed && world.getBlockState(p.pos)!=p.state) throw new IllegalStateException("Vanilla refused placement at "+p.pos);
        }
        for(Placement p:placements) if(p.inventory!=null) {
            if(!(world.getBlockEntity(p.pos) instanceof Inventory inventory)) throw new IllegalStateException("Expected inventory at "+p.pos);
            inventory.clear();for(int slot=0;slot<p.inventory.size();slot++) inventory.setStack(slot,p.inventory.get(slot).copy());inventory.markDirty();
        }
        installing=false;
        if(Controller.TEST && failNextLot) {failNextLot=false;throw new IllegalStateException("Test fault after all geometry/inventories, before callbacks");}
        JsonArray order=new JsonArray();
        if(notify) for(int index=0;index<placements.size();index++) {
            rootIndex=index;Placement p=placements.get(index);BlockState before=old.get(index),state=world.getBlockState(p.pos);
            if(before!=state) {
                if(!before.isOf(state.getBlock()) || before.getBlock() instanceof AbstractRailBlock) before.onStateReplaced(world,p.pos,false);
                state.onBlockAdded(world,p.pos,before,false);
            }
            world.updateNeighbors(p.pos,state.getBlock());
            if(state.hasComparatorOutput()) world.updateComparators(p.pos,state.getBlock());
            before.prepare(world,p.pos,Block.NOTIFY_ALL|Block.SKIP_DROPS);state.updateNeighbors(world,p.pos,Block.NOTIFY_ALL|Block.SKIP_DROPS);state.prepare(world,p.pos,Block.NOTIFY_ALL|Block.SKIP_DROPS);
            order.add(Task.position(p.pos.getX(),p.pos.getY(),p.pos.getZ()));
        }
        JsonObject result=new JsonObject();result.add("blocks",read(world,placements));result.add("notification_order",order);result.addProperty("placements_applied",placements.size());if(events!=null) {result.add("events",events);result.addProperty("deferred_comparator_updates",deferredComparators);}return result;
        } finally {installing=false;events=null;observedWorld=null;observedPlacements=null;rootIndex=-1;}
    }
}
