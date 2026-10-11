package stonebench;

import com.google.gson.*;
import java.util.*;
import net.minecraft.block.*;
import net.minecraft.block.entity.*;
import net.minecraft.fluid.Fluid;
import net.minecraft.registry.Registries;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.*;
import net.minecraft.world.tick.*;
import stonebench.mixin.*;

/** Observed influence set grows through vanilla writes/events, never clipped to a prototype rectangle. */
public final class Observation {
    private static final Set<BlockPos> POSITIONS=new LinkedHashSet<>();
    private static final List<JsonObject> EVENTS=new ArrayList<>();
    private static final List<JsonObject> OPERATION_EVENTS=new ArrayList<>();
    private static final Set<BlockPos> OUTSIDE=new LinkedHashSet<>();
    private static boolean recording;
    private static int internalReads;
    private static long simulationIndex;
    private static int tickIndex;
    private static String phase="between_ticks";
    public static void track(BlockPos pos) {POSITIONS.add(pos.toImmutable());}
    static void begin(long index,int tick,String value) {recording=true;simulationIndex=index;tickIndex=tick;phase=value;EVENTS.clear();}
    static void end() {recording=false;}
    static void start() {EVENTS.clear();OPERATION_EVENTS.clear();}
    static List<JsonObject> currentEvents() {return EVENTS;}
    static List<JsonObject> operationEvents() {return OPERATION_EVENTS;}
    static void phase(String value) {phase=value;}
    public static void event(ServerWorld world,String kind,BlockPos pos,JsonObject detail) {
        if(!recording || world!=Controller.world() || !world.getServer().isOnThread()) return;
        internalReads++;try {Controller.observeBaseline(pos);} finally {internalReads--;}
        track(pos);if(!Controller.prepared(pos)) OUTSIDE.add(pos.toImmutable());
        JsonObject event=new JsonObject();event.addProperty("order",EVENTS.size());event.addProperty("kind",kind);event.addProperty("phase",phase);
        event.addProperty("tick_index",tickIndex);event.addProperty("simulation_index",simulationIndex);event.addProperty("world_time",world.getTime());event.addProperty("time_of_day",world.getTimeOfDay());
        event.addProperty("operation_order",OPERATION_EVENTS.size());event.add("position",Task.position(pos.getX(),pos.getY(),pos.getZ()));event.add("detail",detail);EVENTS.add(event);OPERATION_EVENTS.add(event);
    }
    public static JsonObject detail(String key,String value) {JsonObject detail=new JsonObject();detail.addProperty(key,value);return detail;}
    public static void read(ServerWorld world,BlockPos pos,BlockState state) {
        if(recording && internalReads==0) event(world,"block_state_read",pos,detail("state",state.toString()));
    }
    static BlockPos position(JsonObject p,ServerWorld world) {
        if(!Set.of("x","y","z").equals(p.keySet())) throw new IllegalArgumentException("Position requires x,y,z only");
        return new BlockPos(Task.integer(p,"x",-30000000,30000000),Task.integer(p,"y",world.getBottomY(),world.getTopYInclusive()),Task.integer(p,"z",-30000000,30000000));
    }
    static List<BlockPos> region(JsonObject args,ServerWorld world) {
        if(!args.has("min") || !args.has("max") || !args.get("min").isJsonObject() || !args.get("max").isJsonObject()) throw new IllegalArgumentException("min and max positions required");
        BlockPos min=position(args.getAsJsonObject("min"),world),max=position(args.getAsJsonObject("max"),world);
        long count=(1L+max.getX()-min.getX())*(1L+max.getY()-min.getY())*(1L+max.getZ()-min.getZ());
        if(min.getX()>max.getX() || min.getY()>max.getY() || min.getZ()>max.getZ() || count>1000000) throw new IllegalArgumentException("Region must be ordered and contain at most 1000000 coordinates; split larger regions explicitly");
        List<BlockPos> positions=new ArrayList<>();for(var p:BlockPos.iterate(min,max)) positions.add(p.toImmutable());return positions;
    }
    static JsonObject readRegion(ServerWorld world,List<BlockPos> positions) {
        List<JsonObject> rows=new ArrayList<>();for(BlockPos pos:positions) {track(pos);rows.add(BlockCatalog.read(world,pos));}
        JsonObject result=new JsonObject();result.add("blocks",Artifacts.write("region",rows));result.addProperty("world_time",world.getTime());result.addProperty("time_of_day",world.getTimeOfDay());result.add("coverage",coverage());return result;
    }
    static JsonObject raw(ServerWorld world) {
        internalReads++;try {return rawData(world);} finally {internalReads--;}
    }
    private static JsonObject rawData(ServerWorld world) {
        JsonObject state=new JsonObject(),blocks=new JsonObject();
        // Tick queues include all loaded scheduler chunks. Queue positions grow coverage before block sampling.
        state.add("block_ticks",ticks(world,world.getBlockTickScheduler()));state.add("fluid_ticks",ticks(world,world.getFluidTickScheduler()));
        JsonArray events=new JsonArray();int order=0;
        for(var event:((ObservationWorldAccess)world).stonebench$blockEvents()) {
            track(event.pos());JsonObject row=Task.position(event.pos().getX(),event.pos().getY(),event.pos().getZ());row.addProperty("block",Registries.BLOCK.getId(event.block()).toString());row.addProperty("type",event.type());row.addProperty("data",event.data());row.addProperty("order",order++);events.add(row);
        }
        state.add("block_events",events);
        for(BlockPos pos:POSITIONS) {
            if(!Controller.prepared(pos)) {OUTSIDE.add(pos);continue;}
            blocks.add(pos.getX()+","+pos.getY()+","+pos.getZ(),BlockCatalog.read(world,pos));
        }
        state.add("blocks",blocks);state.add("coverage",coverage());return state;
    }
    private static <T> JsonArray ticks(ServerWorld world,WorldTickScheduler<T> scheduler) {
        List<OrderedTick<T>> all=new ArrayList<>();
        ((ObservationSchedulerAccess<T>)scheduler).stonebench$schedulers().values().forEach(chunk->chunk.getQueueAsStream().forEach(all::add));
        all.sort(Comparator.comparingLong(OrderedTick<T>::triggerTick).thenComparingInt(t->t.priority().getIndex()).thenComparingLong(OrderedTick<T>::subTickOrder));
        JsonArray rows=new JsonArray();for(var tick:all) {
            track(tick.pos());if(!Controller.prepared(tick.pos())) OUTSIDE.add(tick.pos());
            JsonObject row=Task.position(tick.pos().getX(),tick.pos().getY(),tick.pos().getZ());Object type=tick.type();row.addProperty("type",type instanceof Block b?Registries.BLOCK.getId(b).toString():Registries.FLUID.getId((Fluid)type).toString());
            row.addProperty("trigger_tick",tick.triggerTick());row.addProperty("priority",tick.priority().getIndex());row.addProperty("sub_tick_order",tick.subTickOrder());rows.add(row);
        }return rows;
    }
    static JsonObject coverage() {
        JsonObject result=new JsonObject();JsonArray outside=new JsonArray();for(var p:OUTSIDE) outside.add(Task.position(p.getX(),p.getY(),p.getZ()));
        result.addProperty("status",OUTSIDE.isEmpty() && Controller.observationReady()?"observed":"insufficient");result.addProperty("chunks_ready",Controller.observationReady());result.addProperty("tracked_positions",POSITIONS.size());result.add("outside_prepared_chunks",outside);
        result.addProperty("certification",false);result.addProperty("limits","Vanilla writes, neighbor updates, scheduled/block events and tracked positions are observed. Entity constructions and uninstrumented runtime memory are not certified; no proof of universal influence completeness.");return result;
    }
    static JsonObject sample(ServerWorld world,int tick,long index,String samplePhase,JsonObject raw) {
        JsonObject row=new JsonObject();row.addProperty("tick_index",tick);row.addProperty("simulation_index",index);row.addProperty("phase",samplePhase);row.addProperty("world_time",world.getTime());row.addProperty("time_of_day",world.getTimeOfDay());row.addProperty("complete",OUTSIDE.isEmpty() && Controller.observationReady());
        JsonObject state=raw.deepCopy();List<JsonElement> blocks=new ArrayList<>(state.remove("blocks").getAsJsonObject().asMap().values());state.add("blocks",Artifacts.write("snapshot_blocks",blocks));row.add("state",state);
        row.add("events",Artifacts.write("intratick_events",EVENTS));return row;
    }
    static JsonObject compareTraces(JsonObject args) {
        String left=Task.string(args,"left"),right=Task.string(args,"right");
        JsonObject payload=new JsonObject();payload.add("comparison",TraceComparison.compare(left,right));return payload;
    }
}
