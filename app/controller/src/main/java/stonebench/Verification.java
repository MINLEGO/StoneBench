package stonebench;

import com.google.gson.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Frozen request handoff; the owning supervisor alone runs independent Minecraft copies. */
final class Verification {
    private static Path directory;
    private static JsonObject before;
    private static long started;
    static boolean running(){return directory!=null;}
    static JsonObject start(JsonObject args,String attempt,JsonObject snapshot) throws IOException {
        if(running()) throw new IllegalArgumentException("Verification already running");
        String id=Task.string(args,"checkpoint_id");
        CheckpointStorage store=new CheckpointStorage(Path.of("stonebench/checkpoints"));
        JsonObject descriptor=store.descriptor(id),context=store.context(id);
        if(!attempt.equals(context.get("attempt_id").getAsString())) throw new IllegalArgumentException("Checkpoint belongs to another attempt");
        String requestId=UUID.randomUUID().toString();Path candidate=Path.of("stonebench/verifications",requestId);
        JsonObject initial=snapshot.deepCopy();long accepted=System.currentTimeMillis();
        JsonObject request=new JsonObject();request.addProperty("request_id",requestId);request.addProperty("checkpoint_id",id);
        request.addProperty("attempt_id",attempt);request.addProperty("manifest_sha256",descriptor.get("manifest_sha256").getAsString());
        request.add("arguments",args.deepCopy());request.add("working_before",initial);
        Path faults=Path.of("stonebench/verification-test-plan.json");
        if(Controller.TEST && Files.exists(faults)) request.add("test_plan",CheckpointStorage.read(faults));
        try {
            Files.createDirectories(candidate);
            if(Controller.TEST && request.has("test_plan") && request.getAsJsonObject("test_plan").get("scenario").getAsString().equals("publication_failure")) {
                Files.createDirectory(candidate.resolve("request.json"));Files.writeString(candidate.resolve("request.json/blocker"),"test-only publication fault");
            }
            CheckpointStorage.writeAtomic(candidate.resolve("request.json"),request);
        } catch(IOException error){throw new IOException("verification_publication_failed: "+candidate,error);}
        directory=candidate;before=initial;started=accepted;
        return envelope(requestId,"running");
    }
    private static JsonObject envelope(String id,String status){JsonObject value=new JsonObject();value.addProperty("request_id",id);value.addProperty("status",status);JsonObject result=new JsonObject();result.add("verification",value);return result;}
    static JsonObject status(JsonObject args) throws IOException {
        String id=UUID.fromString(Task.string(args,"request_id")).toString();Path path=Path.of("stonebench/verifications",id);
        if(Files.exists(path.resolve("visible.json"))){
            JsonObject visible=CheckpointStorage.read(path.resolve("visible.json"));
            // A visible.json from a build before the concise form has no `faults` and may carry the complete report: status is a read (it also runs in artifact recovery), so it refuses rather than rebuilds.
            if(!visible.has("faults"))throw new IllegalArgumentException("Verification result predates the concise form; start a new attempt and verify again");
            JsonObject result=new JsonObject();result.add("verification",visible);return result;
        }
        if(directory==null || !directory.equals(path))throw new IllegalArgumentException("Unknown verification request");
        JsonObject result=envelope(id,Files.exists(path.resolve("cancel.json"))?"cancelling":"running");
        if(Files.exists(path.resolve("heartbeat.json")))result.getAsJsonObject("verification").add("progress",CheckpointStorage.read(path.resolve("heartbeat.json")));
        return result;
    }
    static JsonObject cancel(JsonObject args) throws IOException {
        JsonObject result=status(args);if(!running() || !directory.getFileName().toString().equals(result.getAsJsonObject("verification").get("request_id").getAsString()))return result;
        CheckpointStorage.writeAtomic(directory.resolve("cancel.json"),new JsonObject());return envelope(directory.getFileName().toString(),"cancelling");
    }
    static JsonObject testConfig(JsonObject args) throws IOException {
        if(!Controller.TEST) throw new IllegalArgumentException("Test-only verification faults");
        String scenario=Task.string(args,"scenario");
        if(!Set.of("none","positive","recurrence2","no_return5","direct_block","direct_inventory","direct_internal","bad_open","publication_failure","publish_watchdog").contains(scenario)) throw new IllegalArgumentException("Unknown verification fault scenario");
        JsonObject result=new JsonObject();result.addProperty("scenario",scenario);result.addProperty("test_only",true);
        CheckpointStorage.writeAtomic(Path.of("stonebench/verification-test-plan.json"),result);return result;
    }
    private static final List<String> SHOWN=List.of("request_id","checkpoint_id","manifest_sha256","status","protocol_version","minecraft_version","verdict","conforms_to_alpha","stop_cause","cycles_executed","transition_ticks","first_difference","recurrence_comparisons","infrastructure_error","limits","wall_seconds","worker_artifacts_available_via_mcp","traces_retained","injected_control_not_natural_recurrence","working_construction_preserved","working_differences");
    private static final List<String> SEVERITY=List.of("satisfied","not_verified","indeterminate","failed");
    /** MCP form of a completed report: verdict, outcome per criterion, faults, measurements and rest per boundary. Rule sources, raw movements, preparation/geometry dumps and the report itself stay in completed.json. */
    static JsonObject agentReport(JsonObject full) {
        JsonObject view=new JsonObject();
        for(String key:SHOWN)if(full.has(key))view.add(key,full.get(key).deepCopy());
        Map<String,JsonObject> outcomes=new LinkedHashMap<>(),faults=new LinkedHashMap<>();
        JsonElement recurrence=full.get("recurrence_comparisons"),difference=withoutLocation(full.get("first_difference"));
        if(full.has("criteria"))for(JsonElement item:full.getAsJsonArray("criteria")) {
            JsonObject row=item.getAsJsonObject();String id=row.get("id").getAsString(),status=row.get("status").getAsString();
            JsonObject outcome=outcomes.computeIfAbsent(id,key->{JsonObject value=new JsonObject();value.addProperty("id",key);value.add("mandatory",row.get("mandatory"));value.addProperty("status",status);return value;});
            if(SEVERITY.indexOf(status)>SEVERITY.indexOf(outcome.get("status").getAsString()))outcome.addProperty("status",status);
            if(row.get("mandatory").getAsBoolean() && !status.equals("satisfied")) {
                JsonObject fault=new JsonObject();
                for(String key:List.of("id","status","mode","boundary","expected","observed","diagnostic"))if(row.has(key))fault.add(key,row.get(key).deepCopy());
                // One entry per fault over its cycles; it keeps the first non-null observed (null when there is none).
                JsonObject same=fault.deepCopy();same.remove("observed");
                JsonObject entry=faults.computeIfAbsent(same.toString(),key->fault);
                if((!entry.has("observed") || entry.get("observed").isJsonNull()) && fault.has("observed"))entry.add("observed",fault.get("observed"));
                if(row.has("cycle")){if(!entry.has("cycles"))entry.add("cycles",new JsonArray());entry.getAsJsonArray("cycles").add(row.get("cycle"));}
            }
        }
        // Evidence already at the root of the answer is not repeated per fault.
        for(JsonObject fault:faults.values())if(fault.has("observed") && (fault.get("observed").equals(recurrence) || fault.get("observed").equals(difference)))fault.remove("observed");
        JsonArray criteria=new JsonArray();outcomes.values().forEach(criteria::add);view.add("criteria",criteria);JsonArray listed=new JsonArray();faults.values().forEach(listed::add);view.add("faults",listed);
        if(full.has("measurements"))view.add("measurements",withoutEvidence(full.get("measurements")));
        JsonArray boundaries=new JsonArray();
        if(full.has("boundaries"))for(JsonElement item:full.getAsJsonArray("boundaries")) {
            JsonObject boundary=item.getAsJsonObject(),operation=boundary.getAsJsonObject("operation"),rest=operation.getAsJsonObject("transition"),shown=new JsonObject();
            for(String key:List.of("mode","cycle","expected_state","trace_complete"))shown.add(key,boundary.get(key));
            shown.add("ticks_executed",operation.get("ticks_executed"));
            JsonObject summary=new JsonObject();for(String key:List.of("status","cause","tick","last_movement_tick","recognition_tick","observed_ticks"))if(rest.has(key))summary.add(key,rest.get(key));
            shown.add("rest",summary);
            shown.add("snapshot",Artifacts.write("verification_boundary_snapshot",List.of(boundary.get("snapshot"))));
            boundaries.add(shown);
        }
        view.add("boundaries",boundaries);return view;
    }
    /** first_difference minus where the verifier found it: what a mode_equivalence fault reports as observed. */
    private static JsonElement withoutLocation(JsonElement value) {
        if(value==null || !value.isJsonObject())return null;
        JsonObject copy=value.getAsJsonObject().deepCopy();for(String key:List.of("mode","boundary","first_tick"))copy.remove(key);return copy;
    }
    /** Measurements keep status, value, gaps, envelopes and timestamps; citations, per-movement samples and exclusion/role lists stay local. */
    private static JsonElement withoutEvidence(JsonElement value) {
        if(value.isJsonArray()){JsonArray copy=new JsonArray();value.getAsJsonArray().forEach(item->copy.add(withoutEvidence(item)));return copy;}
        if(!value.isJsonObject())return value.deepCopy();
        JsonObject copy=new JsonObject();
        for(var entry:value.getAsJsonObject().entrySet())if(!Set.of("sources","movements","excluded","conditional_roles").contains(entry.getKey()))copy.add(entry.getKey(),withoutEvidence(entry.getValue()));
        return copy;
    }
    static JsonObject poll(java.util.function.Supplier<JsonObject> snapshot) throws IOException {
        if(directory==null)return null;
        if(!Files.exists(directory.resolve("result.json"))){
            Path heartbeat=directory.resolve("heartbeat.json");long last=Files.exists(heartbeat)?CheckpointStorage.read(heartbeat).get("owner_time_ms").getAsLong():started;
            if(System.currentTimeMillis()-last<=90_000)return null;
            JsonObject marker=new JsonObject();marker.addProperty("reason","owner_heartbeat_lost");CheckpointStorage.writeAtomic(directory.resolve("cancel.json"),marker);JsonObject lost=new JsonObject();lost.addProperty("request_id",directory.getFileName().toString());lost.addProperty("verdict","infrastructure_error");lost.addProperty("conforms_to_alpha",false);lost.addProperty("stop_cause","owner_heartbeat_lost");lost.addProperty("infrastructure_error","Supervisor heartbeat absent for 90s; retained copies require owned-supervisor recovery");CheckpointStorage.writeAtomic(directory.resolve("result.json"),lost);
        }
        JsonObject report=CheckpointStorage.read(directory.resolve("result.json"));
        JsonObject current=snapshot.get();
        if(Files.exists(directory.resolve("cancel.json"))){JsonObject marker=CheckpointStorage.read(directory.resolve("cancel.json"));String reason=marker.has("reason")?marker.get("reason").getAsString():"user_cancelled";JsonObject error=new JsonObject();error.addProperty("kind",reason.startsWith("individual_phase_watchdog:")?"phase_timeout":"cancelled");error.addProperty("diagnostic",reason);if(report.has("infrastructure_error"))error.add("worker_error",report.get("infrastructure_error"));report.add("infrastructure_error",error);report.addProperty("verdict","infrastructure_error");report.addProperty("conforms_to_alpha",false);report.addProperty("stop_cause",reason.startsWith("individual_phase_watchdog:")?"individual_phase_watchdog":reason.equals("owner_heartbeat_lost")?reason:"verification_interrupted");}
        report.addProperty("status","completed");
        // Local audit binding, taken from the controller-owned request rather than the worker report.
        JsonObject request=CheckpointStorage.read(directory.resolve("request.json")),audit=new JsonObject();
        for(String key:List.of("attempt_id","request_id","checkpoint_id","manifest_sha256"))audit.add(key,request.get(key));
        report.add("audit",audit);
        JsonArray differences=ObservationComparison.fields(before,current);
        report.addProperty("working_construction_preserved",differences.isEmpty());
        report.add("working_differences",differences);report.add("working_after",current.deepCopy());
        if(!differences.isEmpty()) {report.addProperty("verdict","infrastructure_error");report.addProperty("conforms_to_alpha",false);}
        if(report.has("measurements")) report.getAsJsonObject("measurements").addProperty("interpretation",report.get("conforms_to_alpha").getAsBoolean()?"conforms_to_alpha_measurements":"alpha_diagnostic");
        CheckpointStorage.writeAtomic(directory.resolve("completed.json"),report);
        JsonObject result=new JsonObject();result.add("verification",publish(directory,report));directory=null;before=null;return result;
    }
    /** Writes the concise answer beside the local report and returns it. */
    private static JsonObject publish(Path request,JsonObject report) throws IOException {
        JsonObject visible=agentReport(report);
        visible.add("working_after",Artifacts.write("verification_working_after",List.of(report.get("working_after"))));
        CheckpointStorage.writeAtomic(request.resolve("visible.json"),visible);return visible;
    }
}
