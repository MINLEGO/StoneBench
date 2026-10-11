package stonebench;

import com.google.gson.*;
import java.util.*;
import net.minecraft.block.*;
import net.minecraft.block.enums.BlockFace;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.state.property.Properties;
import net.minecraft.util.math.*;

/** External vanilla drivers; never alter power, tick deadlines or natural button duration. */
public final class Inputs {
    private static BlockPos position, input, driver;
    private static Direction outward;
    private static String device, mode="direct";
    private static boolean armed, sampling;
    private static int sourcePower,inputPower;
    private static final Set<BlockPos> ADAPTER=new LinkedHashSet<>();
    static void stop() {armed=false;}
    public static boolean adapter(BlockPos pos) {return ADAPTER.contains(pos);}
    static Set<ChunkPos> chunks() {
        Set<ChunkPos> result=new LinkedHashSet<>();
        for(int n=0;n<=3;n++) for(int dx=-2;dx<=2;dx++) for(int dz=-2;dz<=2;dz++) result.add(new ChunkPos(input.offset(outward,n).add(dx,0,dz)));
        return result;
    }
    static JsonObject declare(ServerWorld world,JsonObject args) {
        if(!args.has("position") || !args.get("position").isJsonObject() || !args.has("input_block") || !args.get("input_block").isJsonObject()) throw new IllegalArgumentException("position and input_block must be coordinate objects");
        BlockPos p=Observation.position(args.getAsJsonObject("position"),world),i=Observation.position(args.getAsJsonObject("input_block"),world);
        Direction direction=Direction.byId(Task.string(args,"orientation"));
        if(direction==null || !direction.getAxis().isHorizontal()) throw new IllegalArgumentException("Input orientation must be a lateral cardinal direction; up/down forbidden");
        String selected=Task.string(args,"device");BlockCatalog.Entry entry=BlockCatalog.entry(selected);
        if(!(entry.block() instanceof LeverBlock || entry.block() instanceof ButtonBlock)) throw new IllegalArgumentException("Input requires a catalog lever/button");
        if(!p.equals(i.offset(direction))) throw new IllegalArgumentException("Device must be adjacent to input block in outward orientation");
        if(!Observation.coverage().get("status").getAsString().equals("observed")) throw new IllegalArgumentException("Input declaration needs complete prepared observation coverage");
        if(!ADAPTER.isEmpty()) throw new IllegalArgumentException("Existing adapter must be removed with modify_blocks before redeclaration");
        BlockState state=world.getBlockState(p);
        if(!state.isOf(entry.block()) || state.get(Properties.BLOCK_FACE)!=BlockFace.WALL || state.get(Properties.HORIZONTAL_FACING)!=direction || !state.canPlaceAt(world,p)) throw new IllegalArgumentException("Device must have vanilla wall support and declared orientation");
        if(state.get(Properties.POWERED) || world.getReceivedRedstonePower(i)!=0) throw new IllegalArgumentException("Declaration requires unpowered input/device");
        if(world.getBlockState(i).isAir()) throw new IllegalArgumentException("Input block must belong to construction");
        // A lateral surface is on the live observed construction envelope, excluding this device.
        JsonObject blocks=Observation.raw(world).getAsJsonObject("blocks");
        int plane=direction.getAxis()==Direction.Axis.X?i.getX():i.getZ();
        for(var value:blocks.entrySet()) {
            JsonObject row=value.getValue().getAsJsonObject();BlockPos other=new BlockPos(row.get("x").getAsInt(),row.get("y").getAsInt(),row.get("z").getAsInt());
            if(other.equals(p) || adapter(other) || row.get("block").getAsString().equals("minecraft:air")) continue;
            int coordinate=direction.getAxis()==Direction.Axis.X?other.getX():other.getZ();
            if((coordinate-plane)*direction.getDirection().offset()>0) throw new IllegalArgumentException("Input is not on the exterior lateral construction envelope");
        }
        position=p;input=i;driver=p;outward=direction;device=selected;mode="direct";ADAPTER.add(p);
        Observation.track(p);Observation.track(i);return describe();
    }
    static void modified(List<Construction.Placement> placements) {
        if(position==null) return;
        if(placements.stream().anyMatch(p->ADAPTER.contains(p.pos()) || p.pos().equals(input))) {position=null;input=null;driver=null;ADAPTER.clear();sampling=false;stop();}
    }
    static void requireDeclared(ServerWorld world) {
        if(position==null) throw new IllegalArgumentException("declare_input is required");
        BlockState state=world.getBlockState(driver);
        if(!state.isOf(BlockCatalog.entry(device).block()) || !state.canPlaceAt(world,driver)) throw new IllegalArgumentException("Declared device/support changed");
    }
    static JsonObject prepare(ServerWorld world,String selected) {
        requireDeclared(world);
        if(!Set.of("direct","repeater").contains(selected)) throw new IllegalArgumentException("mode must be direct or repeater");
        if(!mode.equals("direct") || !selected.equals("repeater")) {
            if(mode.equals(selected)) {JsonObject result=describe();result.addProperty("construction_preserved",true);return result;}
            throw new IllegalArgumentException("Restore/rebuild the declared direct state before changing mode");
        }
        if(world.getBlockState(driver).get(Properties.POWERED) || world.getReceivedRedstonePower(input)!=0) throw new IllegalArgumentException("Adapter preparation requires inactive input");
        BlockPos support=position.offset(outward),remote=support.offset(outward),floor=position.down();
        for(BlockPos pos:List.of(support,remote,floor)) if(!world.getBlockState(pos).isAir()) throw new IllegalArgumentException("External adapter needs three vacant coordinates: "+pos);
        for(BlockPos center:List.of(position,support,remote,floor)) for(BlockPos nearby:BlockPos.iterate(center.add(-2,-2,-2),center.add(2,2,2))) Observation.track(nearby);
        ADAPTER.addAll(List.of(support,remote,floor));
        JsonObject before=construction(Observation.raw(world));
        for(BlockPos pos:ADAPTER) Observation.track(pos);
        Controller.inputMutation();
        world.setBlockState(position,Blocks.AIR.getDefaultState(),Block.NOTIFY_ALL);
        world.setBlockState(floor,Blocks.STONE.getDefaultState(),Block.NOTIFY_ALL);
        world.setBlockState(support,Blocks.STONE.getDefaultState(),Block.NOTIFY_ALL);
        world.setBlockState(position,Blocks.REPEATER.getDefaultState().with(Properties.HORIZONTAL_FACING,outward).with(Properties.DELAY,1),Block.NOTIFY_ALL);
        world.setBlockState(remote,BlockCatalog.entry(device).block().getDefaultState().with(Properties.BLOCK_FACE,BlockFace.WALL).with(Properties.HORIZONTAL_FACING,outward),Block.NOTIFY_ALL);
        driver=remote;mode=selected;
        JsonObject after=construction(Observation.raw(world)),result=describe();JsonArray differences=ObservationComparison.fields(before,after);
        result.add("preservation_differences",Artifacts.write("input_preservation_diff",differences.asList()));result.addProperty("construction_preserved",differences.isEmpty());
        result.add("construction_before",before);result.add("construction_after",after);
        if(!differences.isEmpty()) throw new IllegalStateException("Adapter preparation altered initial construction; inspect operation artifacts");
        return result;
    }
    static void arm(ServerWorld world) {requireDeclared(world);if(world.getBlockState(driver).getBlock() instanceof ButtonBlock && world.getBlockState(driver).get(Properties.POWERED)) throw new IllegalArgumentException("Button is active; advance until its natural release before pressing again");armed=true;sampling=true;sourcePower=world.getBlockState(driver).get(Properties.POWERED)?15:0;inputPower=world.getReceivedRedstonePower(input);}
    public static void beforeTime(ServerWorld world) {
        if(!armed || world!=Controller.world()) return;
        armed=false;Controller.observationPhase("before_world_time");
        JsonObject detail=describe();Observation.event(world,"input_interaction",driver,detail);
        BlockState state=world.getBlockState(driver);
        if(state.getBlock() instanceof LeverBlock lever) lever.togglePower(state,world,driver,null);
        else ((ButtonBlock)state.getBlock()).powerOn(state,world,driver,null);
        changed(world);
    }
    public static void changed(ServerWorld world) {
        if(!sampling || world!=Controller.world()) return;
        BlockState driverState=world.getBlockState(driver);
        if(!driverState.contains(Properties.POWERED)) {sampling=false;Observation.event(world,"input_device_invalidated",driver,new JsonObject());return;}
        int source=driverState.get(Properties.POWERED)?15:0,signal=world.getReceivedRedstonePower(input);
        if(source!=sourcePower) {sourcePower=source;edge(world,"input_device_change",driver,source);}
        if(signal!=inputPower) {inputPower=signal;edge(world,"input_signal_change",input,signal);}
    }
    private static void edge(ServerWorld world,String kind,BlockPos pos,int power) {JsonObject detail=new JsonObject();detail.addProperty("power",power);Observation.event(world,kind,pos,detail);}
    public static JsonObject declared() {return position==null?null:describe();}
    public static boolean expectedExternalEvent(BlockPos pos) {return position!=null && ((device.endsWith("_button") && pos.equals(driver)) || (mode.equals("repeater") && pos.equals(position)));}
    static JsonObject describe() {JsonObject result=new JsonObject();result.addProperty("device",device);result.addProperty("mode",mode);result.add("position",Task.position(position.getX(),position.getY(),position.getZ()));result.add("driver",Task.position(driver.getX(),driver.getY(),driver.getZ()));result.add("input_block",Task.position(input.getX(),input.getY(),input.getZ()));result.addProperty("orientation",outward.asString());result.add("support",Task.position(input.getX(),input.getY(),input.getZ()));result.addProperty("face","wall");result.addProperty("validation","validated_lateral_exterior");JsonArray boundary=new JsonArray();for(BlockPos p:ADAPTER) boundary.add(Task.position(p.getX(),p.getY(),p.getZ()));result.add("adapter_positions",boundary);return result;}
    /** Partition, retaining exact records and absolute scheduled deadlines/order in each owner. */
    static JsonObject construction(JsonObject raw) {
        JsonObject copy=raw.deepCopy(),blocks=copy.getAsJsonObject("blocks");
        for(BlockPos pos:ADAPTER) blocks.remove(pos.getX()+","+pos.getY()+","+pos.getZ());
        for(String key:List.of("block_ticks","fluid_ticks","block_events")) {JsonArray rows=new JsonArray();for(JsonElement item:copy.getAsJsonArray(key)) {JsonObject row=item.getAsJsonObject();if(!adapter(new BlockPos(row.get("x").getAsInt(),row.get("y").getAsInt(),row.get("z").getAsInt()))) rows.add(item);}copy.add(key,rows);}
        copy.remove("coverage");return copy;
    }
}
