package stonebench;

import com.google.gson.*;
import java.util.*;
import net.minecraft.block.*;
import net.minecraft.block.entity.BlockEntity;
import net.minecraft.inventory.Inventory;
import net.minecraft.item.*;
import net.minecraft.registry.Registries;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.state.property.Property;
import net.minecraft.util.Identifier;
import net.minecraft.util.math.BlockPos;

/** Explicit construction coverage, never a conformity restriction. No raw state or NBT input. */
final class BlockCatalog {
    record Entry(Block block, Set<String> parameters, int slots) {}
    static final Map<String,Entry> ENTRIES=new LinkedHashMap<>();
    // One add() per run of consecutive ids, in the published order of docs/blocs-a-prendre-en-charge.md.
    static {
        add("air quartz_block white_wool orange_wool magenta_wool light_blue_wool yellow_wool lime_wool pink_wool gray_wool light_gray_wool cyan_wool purple_wool blue_wool brown_wool green_wool red_wool black_wool obsidian honey_block slime_block sand",0);
        add("smooth_stone_slab",0,"type"); add("stone_stairs",0,"facing","half");
        add("glass glass_pane water scaffolding stone_brick_wall",0);
        add("player_head",0,"rotation"); add("beacon",0); add("oak_log",0,"axis"); add("oak_leaves",0);
        add("piston sticky_piston observer",0,"facing"); add("dispenser dropper",9,"facing");
        add("repeater",0,"facing","delay"); add("comparator",0,"facing","mode");
        add("redstone_wire redstone_torch",0); add("redstone_wall_torch",0,"facing");
        add("stone_button oak_button lever",0,"face","facing");
        add("stone_pressure_plate oak_pressure_plate light_weighted_pressure_plate heavy_weighted_pressure_plate redstone_block redstone_lamp target",0);
        add("note_block",0,"note");
        add("hopper",5,"facing"); add("chest trapped_chest barrel",27,"facing");
        add("composter",0,"level");
        add("iron_trapdoor",0,"facing","half"); add("oak_trapdoor",0,"facing","half","open");
        add("iron_door",0,"facing","hinge"); add("oak_door",0,"facing","hinge","open"); add("oak_fence_gate",0,"facing","open");
        add("furnace",3,"facing"); add("shulker_box",27,"facing");
        add("rail powered_rail detector_rail activator_rail waxed_copper_grate",0);
    }
    private static void add(String ids,int slots,String... allowed) {
        for(String id:ids.split(" ")) {
            if(!Registries.BLOCK.containsId(Identifier.ofVanilla(id))) throw new IllegalStateException("Unknown vanilla block in catalog: "+id);
            Block block=Registries.BLOCK.get(Identifier.ofVanilla(id));
            Set<String> parameters=new LinkedHashSet<>();
            for(Property<?> p:block.getStateManager().getProperties()) if(p.getName().equals("waterlogged") || List.of(allowed).contains(p.getName())) parameters.add(p.getName());
            ENTRIES.put("minecraft:"+id,new Entry(block,parameters,slots));
        }
    }
    static Entry entry(String id) {
        Entry entry=ENTRIES.get(id);
        if(entry==null) throw new UnsupportedOperationException("unsupported_component: "+id+" is outside the published construction catalog; this does not declare it nonconforming");
        return entry;
    }
    static final String HOPPER_COVERAGE="Known hopper memory observed; behavioral restoration remains indeterminate until a differential replay establishes it";
    static final String PISTON_COVERAGE="Moving piston NBT and dedicated-server progress/time observed; saving in motion is not certified";
    static final String BLOCK_ENTITY_COVERAGE="Serialized NBT observed; completeness of nonserialized memory not certified";
    /** Global list only: ids in published order, no detail. */
    static JsonObject describe() {
        JsonObject result=new JsonObject(); JsonArray catalog=new JsonArray();
        for(String id:ENTRIES.keySet()) catalog.add(id);
        result.add("catalog",catalog);
        return result;
    }
    /** One block on demand; an unknown or withdrawn id is unsupported_component, never the full catalog. */
    static JsonObject describeBlock(String id) {
        Entry entry=entry(id);
        JsonObject row=new JsonObject(),configurable=new JsonObject(),computed=new JsonObject();row.addProperty("id",id);
        for(Property<?> p:entry.block.getStateManager().getProperties()) {
            JsonArray values=new JsonArray(); for(Object value:p.getValues()) values.add(name(p,value));
            (entry.parameters.contains(p.getName())?configurable:computed).add(p.getName(),values);
        }
        if(entry.block instanceof HopperBlock) {JsonObject field=new JsonObject();field.addProperty("source","block_entity_runtime");field.addProperty("editable",false);field.addProperty("observation","Typed read-only runtime fields are included in read_blocks/region and tick snapshots; faithful restoration and rest remain indeterminate");computed.add("cooldown",field);computed.add("last_tick_time",field.deepCopy());}
        row.add("configurable",configurable);row.add("computed",computed);row.addProperty("inventory_slots",entry.slots);
        row.addProperty("coverage","Explicit supported block ids only; unsupported components are errors, never implicit conformity rules");
        if(entry.slots>0) row.addProperty("inventory_contract","Vanilla registered items without data components, 1..item maximum stack size, unique slots; no NBT or internal block-entity fields");
        if(entry.block instanceof HopperBlock) row.addProperty("runtime_coverage",HOPPER_COVERAGE);
        else if(entry.block instanceof PistonBlock) row.addProperty("runtime_coverage",PISTON_COVERAGE);
        else if(entry.block instanceof BlockEntityProvider) row.addProperty("runtime_coverage",BLOCK_ENTITY_COVERAGE);
        return row;
    }
    @SuppressWarnings({"rawtypes","unchecked"}) static String name(Property p,Object value) {return p.name((Comparable)value);}
    @SuppressWarnings({"rawtypes","unchecked"}) static BlockState parameters(BlockState state,JsonObject args,Entry entry) {
        for(var pair:args.entrySet()) {
            if(!entry.parameters.contains(pair.getKey())) throw new IllegalArgumentException("Not a configurable in-game parameter: "+pair.getKey());
            if(!pair.getValue().isJsonPrimitive() || !pair.getValue().getAsJsonPrimitive().isString()) throw new IllegalArgumentException("Parameter values must be catalog strings");
            Property p=state.getBlock().getStateManager().getProperty(pair.getKey());
            Optional value=p.parse(pair.getValue().getAsString());
            if(value.isEmpty()) throw new IllegalArgumentException("Invalid parameter value: "+pair);
            state=state.with(p,(Comparable)value.get());
        }
        return state;
    }
    static List<ItemStack> inventory(JsonElement raw,Entry entry,BlockPos pos,BlockState state,ServerWorld world) {
        if(raw==null) return null;
        if(entry.slots==0 || !raw.isJsonArray()) throw new IllegalArgumentException("inventory requires a covered inventory block and an array");
        List<ItemStack> stacks=new ArrayList<>(Collections.nCopies(entry.slots,ItemStack.EMPTY));Set<Integer> used=new HashSet<>();
        BlockEntity entity=((BlockEntityProvider)entry.block).createBlockEntity(pos,state);
        entity.setWorld(world); Inventory inventory=(Inventory)entity;
        for(JsonElement value:raw.getAsJsonArray()) {
            if(!value.isJsonObject()) throw new IllegalArgumentException("Inventory entry must be an object");JsonObject row=value.getAsJsonObject();
            if(!Set.of("slot","item","count").equals(row.keySet())) throw new IllegalArgumentException("Inventory accepts slot, item, count only");
            int slot=Task.integer(row,"slot",0,entry.slots-1);if(!used.add(slot)) throw new IllegalArgumentException("Duplicate inventory slot");
            Identifier id=Identifier.tryParse(Task.string(row,"item"));
            if(id==null || !Registries.ITEM.containsId(id) || Registries.ITEM.get(id)==Items.AIR) throw new IllegalArgumentException("Unknown or empty item");
            ItemStack stack=new ItemStack(Registries.ITEM.get(id));int count=Task.integer(row,"count",1,Math.min(stack.getMaxCount(),inventory.getMaxCountPerStack()));stack.setCount(count);
            if(!inventory.isValid(slot,stack)) throw new IllegalArgumentException("Item invalid for vanilla inventory slot");stacks.set(slot,stack);
        }
        return stacks;
    }
    static JsonObject read(ServerWorld world,BlockPos pos) {
        JsonObject row=Task.position(pos.getX(),pos.getY(),pos.getZ());BlockState state=world.getBlockState(pos);
        row.addProperty("state",state.toString());row.addProperty("block",Registries.BLOCK.getId(state.getBlock()).toString());
        JsonObject parameters=new JsonObject();for(var pair:state.getEntries().entrySet()) parameters.addProperty(pair.getKey().getName(),name(pair.getKey(),pair.getValue()));row.add("parameters",parameters);row.add("measurement",Measurement.block(world,pos,state));
        JsonArray inventory=new JsonArray();if(world.getBlockEntity(pos) instanceof Inventory inv) for(int slot=0;slot<inv.size();slot++) {
            ItemStack stack=inv.getStack(slot);if(stack.isEmpty()) continue;JsonObject item=new JsonObject();item.addProperty("slot",slot);item.addProperty("item",Registries.ITEM.getId(stack.getItem()).toString());item.addProperty("count",stack.getCount());inventory.add(item);
        }
        row.add("inventory",inventory);
        BlockEntity entity=world.getBlockEntity(pos);
        if(entity!=null) {
            row.add("nbt",TypedNbt.encode(entity.createNbtWithIdentifyingData(world.getRegistryManager())));
            row.addProperty("block_entity_type",Registries.BLOCK_ENTITY_TYPE.getId(entity.getType()).toString());
            if(entity instanceof net.minecraft.block.entity.HopperBlockEntity) {
                var access=(stonebench.mixin.ObservationHopperAccess)entity;JsonObject runtime=new JsonObject();
                runtime.addProperty("last_tick_time",Long.toString(access.stonebench$lastTickTime()));runtime.addProperty("last_tick_time_type","long");
                runtime.addProperty("transfer_cooldown",access.stonebench$cooldown());row.add("runtime",runtime);
                row.addProperty("runtime_coverage",HOPPER_COVERAGE);
            } else if(entity instanceof net.minecraft.block.entity.PistonBlockEntity) {
                var access=(stonebench.mixin.ObservationPistonAccess)entity;JsonObject runtime=new JsonObject();
                runtime.addProperty("progress",Float.toString(access.stonebench$progress()));runtime.addProperty("last_progress",Float.toString(access.stonebench$lastProgress()));runtime.addProperty("saved_world_time",Long.toString(access.stonebench$savedWorldTime()));
                runtime.addProperty("progress_type","float");runtime.addProperty("saved_world_time_type","long");row.add("runtime",runtime);row.addProperty("runtime_coverage",PISTON_COVERAGE);
            } else row.addProperty("runtime_coverage",BLOCK_ENTITY_COVERAGE);
        }
        return row;
    }
}

