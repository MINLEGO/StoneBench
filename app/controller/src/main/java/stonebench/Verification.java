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
        if(Files.exists(path.resolve("visible.json"))){JsonObject result=new JsonObject();result.add("verification",CheckpointStorage.read(path.resolve("visible.json")));return result;}
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
        JsonArray differences=ObservationComparison.fields(before,current);
        report.addProperty("working_construction_preserved",differences.isEmpty());
        report.add("working_differences",differences);report.add("working_after",current.deepCopy());
        if(!differences.isEmpty()) {report.addProperty("verdict","infrastructure_error");report.addProperty("conforms_to_alpha",false);}
        CheckpointStorage.writeAtomic(directory.resolve("completed.json"),report);
        JsonObject visible=report.deepCopy();visible.add("full_report",Artifacts.write("verification_report",List.of(report)));
        visible.add("working_after",Artifacts.write("verification_working_after",List.of(current)));
        if(visible.has("boundaries")) for(JsonElement item:visible.getAsJsonArray("boundaries")) {
            JsonObject boundary=item.getAsJsonObject();
            boundary.add("snapshot",Artifacts.write("verification_boundary_snapshot",List.of(boundary.get("snapshot"))));
        }
        CheckpointStorage.writeAtomic(directory.resolve("visible.json"),visible);
        JsonObject result=new JsonObject();result.add("verification",visible);directory=null;before=null;return result;
    }
}
