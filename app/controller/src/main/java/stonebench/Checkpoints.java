package stonebench;

import com.google.gson.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Rest evidence and persisted reprise context. Server-thread lifecycle is owned by Controller. */
public final class Checkpoints {
    private static JsonObject restSnapshot,restReport;
    private static final CheckpointStorage STORAGE=new CheckpointStorage(Path.of("stonebench/checkpoints"));
    private Checkpoints() {}

    public static JsonObject snapshot(JsonObject raw,long worldTime,long timeOfDay) {
        JsonObject result=new JsonObject();result.addProperty("world_time",worldTime);result.addProperty("time_of_day",timeOfDay);
        result.add("state",raw.deepCopy());return result;
    }

    /** Called only for a genuine completed transition; never infers rest from a frozen world. */
    public static void recordRest(JsonObject snapshot,JsonObject report) {
        if(!"terminated".equals(report.get("status").getAsString())) {invalidateRest();return;}
        restSnapshot=snapshot.deepCopy();restReport=report.deepCopy();
    }
    public static void invalidateRest() {restSnapshot=null;restReport=null;}

    public static JsonObject create(Path world,JsonObject current,JsonObject context,JsonObject provenance,boolean frozen,Runnable flush) throws IOException {
        requireRest(current,frozen);
        flush.run();
        JsonObject savedContext=context.deepCopy();savedContext.add("rest",restReport.deepCopy());
        JsonObject savedProvenance=provenance.deepCopy();savedProvenance.add("memory_coverage",memoryCoverage(current));
        JsonObject checkpoint=STORAGE.create(world,savedContext,current,savedProvenance);
        JsonObject result=new JsonObject();result.add("checkpoint",checkpoint);result.addProperty("checkpoint_status","created");
        result.addProperty("door_conformity_required",false);result.addProperty("rest_established",true);
        result.addProperty("fidelity_scope","Observed static components only; compare loaded state before replay; no universal JVM capture");
        return result;
    }

    static void requireRest(JsonObject current,boolean frozen) {
        if(!frozen) throw new IllegalArgumentException("checkpoint_requires_frozen_between_ticks");
        if(restSnapshot==null) throw new IllegalArgumentException("checkpoint_requires_established_rest: call transition first");
        if(!CheckpointComparison.complete(current)) throw new IllegalArgumentException("checkpoint_indeterminate_observation_coverage");
        if(!ObservationComparison.fields(restSnapshot,current).isEmpty()) throw new IllegalArgumentException("checkpoint_rest_evidence_stale: state or clocks changed since rest");
        JsonObject coverage=memoryCoverage(current);
        if(!coverage.get("restorable_observed_scope").getAsBoolean()) throw new IllegalArgumentException("checkpoint_indeterminate_runtime_memory: "+coverage.get("uncovered_components"));
        for(String queue:List.of("block_ticks","fluid_ticks","block_events")) if(!current.getAsJsonObject("state").getAsJsonArray(queue).isEmpty()) throw new IllegalArgumentException("checkpoint_pending_"+queue);
    }

    static JsonObject memoryCoverage(JsonObject snapshot) {
        JsonArray uncovered=new JsonArray();
        try {
            for(var entry:snapshot.getAsJsonObject("state").getAsJsonObject("blocks").entrySet()) {
                JsonObject block=entry.getValue().getAsJsonObject();String id=block.get("block").getAsString();
                String entity=block.has("block_entity_type")?block.get("block_entity_type").getAsString():"";
                if(id.equals("minecraft:moving_piston") || !entity.isEmpty() && !entity.equals("minecraft:chest")) uncovered.add(entry.getKey()+":"+(entity.isEmpty()?id:entity));
                // Burnout histories are JVM-only; stable torch block state does not prove restart fidelity.
                if(Set.of("minecraft:redstone_torch","minecraft:redstone_wall_torch").contains(id)) uncovered.add(entry.getKey()+":"+id+":burnout_history_not_serialized");
            }
        } catch(RuntimeException e) {uncovered.add("missing_complete_block_records");}
        JsonObject result=new JsonObject();result.addProperty("restorable_observed_scope",uncovered.isEmpty());
        result.add("uncovered_components",uncovered);
        JsonArray memory=new JsonArray();
        memory.add("Moving piston runtime progress/saved time: observed, checkpoints in motion rejected");
        memory.add("Hopper last_tick_time: observed but nonserialized effect/reprise unestablished, rejected");
        memory.add("Redstone torch burnout history: nonserialized and unobserved, rejected");
        memory.add("Chest viewers/lid animation/cache: new process resets them; no players and closed ordinary chest fixture only");
        memory.add("World scheduler sub-tick counter: process-local; no pending work at capture; exact subsequent order remains compared");
        memory.add("Block events/neighbor propagation: process-local; required empty/drained between operations");
        memory.add("Observation influence and input sampling ownership: persisted explicitly in controller context");
        memory.add("Entity state, arbitrary JVM memory and all RNG streams: outside proof scope; no universal claim");
        result.add("memory_inventory",memory);result.addProperty("universal_capture",false);return result;
    }

    public static JsonObject list() throws IOException {JsonObject result=new JsonObject();result.add("checkpoints",STORAGE.list());return result;}
    public static JsonObject requestRestore(String id,Path serverRoot,String attemptId) throws IOException {
        JsonObject result=STORAGE.requestRestore(id,serverRoot,attemptId);
        invalidateRest();result.addProperty("reconnect","Reconnect to the same MCP endpoint after supervisor restart; inspect describe_task.restoration before further mutation");return result;
    }
    public static JsonObject context(String id) throws IOException {return STORAGE.context(id);}
    public static JsonObject expectedState(String id) throws IOException {return STORAGE.state(id);}

    public static JsonObject compareRestored(String id,JsonObject actual) throws IOException {
        JsonObject expected=expectedState(id),result=CheckpointComparison.compare(expected,actual);
        result.addProperty("checkpoint_id",id);result.addProperty("useful_ticks_before_comparison",0);
        if(result.get("status").getAsString().equals("equal")) recordRest(actual,context(id).getAsJsonObject("rest"));
        else invalidateRest();
        return result;
    }
}
