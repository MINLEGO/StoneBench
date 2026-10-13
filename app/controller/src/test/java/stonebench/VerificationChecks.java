package stonebench;

import com.google.gson.*;
import java.util.*;

/** The MCP form of a completed verification report: outcomes and measurements kept, citations and raw evidence local. Not Minecraft validation. */
public final class VerificationChecks {
    static JsonObject row(String id,String status,boolean mandatory,String mode,int cycle,String boundary,JsonElement observed) {
        JsonObject row=Rules.diagnostic(id,status,observed,"diagnostic "+id);row.addProperty("mandatory",mandatory);
        row.addProperty("mode",mode);row.addProperty("cycle",cycle);row.addProperty("boundary",boundary);return row;
    }
    static JsonObject metric(String status,JsonElement value,String gap) {
        JsonObject metric=new JsonObject();metric.addProperty("status",status);metric.add("value",value);
        JsonArray sources=new JsonArray();sources.add(Rules.reference(Task.RULES,"community",Rules.REVISION,"native_character_index","23868"));metric.add("sources",sources);
        JsonArray gaps=new JsonArray();if(gap!=null)gaps.add(gap);metric.add("gaps",gaps);
        JsonArray movements=new JsonArray();movements.add(new JsonObject());metric.add("movements",movements);metric.add("excluded",new JsonArray());metric.add("conditional_roles",new JsonArray());return metric;
    }
    static JsonObject boundary(String mode,String state) {
        JsonObject operation=new JsonObject(),rest=new JsonObject();rest.addProperty("status","terminated");rest.addProperty("tick",7);rest.addProperty("recognition_tick",7);rest.addProperty("rest_scope","x");
        operation.add("transition",rest);operation.addProperty("ticks_executed",7);operation.add("trace",new JsonObject());
        JsonObject snapshot=new JsonObject();snapshot.addProperty("world_time",35);
        JsonObject entry=new JsonObject();entry.addProperty("mode",mode);entry.addProperty("cycle",1);entry.addProperty("expected_state",state);entry.addProperty("trace_complete",true);
        entry.add("operation",operation);entry.add("snapshot",snapshot);entry.add("geometry",Rules.describe());entry.add("criteria",new JsonArray());return entry;
    }
    static void require(boolean ok,String message){GeometryChecks.require(ok,message);}
    static JsonObject arguments(String id){JsonObject args=new JsonObject();args.addProperty("artifact_id",id);args.addProperty("offset",0);args.addProperty("limit",1);return args;}
    public static void main(String[] args) {
        JsonObject full=new JsonObject();
        for(String key:List.of("request_id","checkpoint_id","manifest_sha256","protocol_version"))full.addProperty(key,"value-of-"+key.replace("_sha256","_digest"));
        full.addProperty("status","completed");full.addProperty("verdict","failed");full.addProperty("conforms_to_alpha",false);full.addProperty("stop_cause","invalid_repeater_boundary");full.addProperty("cycles_executed",1);
        full.add("first_difference",JsonNull.INSTANCE);full.add("audit",new JsonObject());full.add("checkpoint_provenance",Rules.describe());full.add("copies",new JsonArray());
        full.addProperty("retained_worker_directory","local-worker-directory");full.add("working_after",new JsonObject());
        JsonArray criteria=new JsonArray();
        criteria.add(row("fixed_passage","satisfied",true,"repeater",1,"open",JsonNull.INSTANCE));
        criteria.add(row("frame_state","failed",true,"repeater",1,"open",JsonParser.parseString("[{\"x\":1024}]")));
        criteria.add(row("fixed_passage","satisfied",true,"repeater",1,"closed",JsonNull.INSTANCE));
        criteria.add(row("continuable","indeterminate",true,"repeater",1,"closed",JsonNull.INSTANCE));
        criteria.add(row("frame_state","satisfied",true,"repeater",1,"closed",JsonNull.INSTANCE));
        criteria.add(row("record_reliability","not_verified",false,"repeater",1,"closed",JsonNull.INSTANCE));
        full.add("criteria",criteria);
        JsonObject measurements=new JsonObject(),transition=new JsonObject();measurements.add("dynamic_volume",metric("indeterminate",JsonNull.INSTANCE,"conditional_role_exclusion_changes_dimensions"));
        measurements.add("opening_time",metric("measured",new JsonPrimitive(6),null));transition.add("opening_time",metric("measured",new JsonPrimitive(6),null));transition.add("dynamic_volume",metric("indeterminate",JsonNull.INSTANCE,"gap"));
        transition.addProperty("mode","repeater");JsonArray transitions=new JsonArray();transitions.add(transition);measurements.add("transitions",transitions);full.add("measurements",measurements);
        JsonArray boundaries=new JsonArray();boundaries.add(boundary("repeater","open"));full.add("boundaries",boundaries);
        // Negative control: the complete report is full of citations, so the detector must find them.
        boolean found=false;try{GeometryChecks.noSources(full,"full");}catch(AssertionError expected){found=true;}require(found,"The citation detector must flag the complete report");

        JsonObject view=Verification.agentReport(full);GeometryChecks.noSources(view,"verification_status");
        for(String key:List.of("audit","checkpoint_provenance","copies","retained_worker_directory","working_after"))require(!view.has(key),key+" stays local");
        for(String key:List.of("request_id","checkpoint_id","manifest_sha256","verdict","conforms_to_alpha","stop_cause","cycles_executed"))require(view.get(key).equals(full.get(key)),key+" kept");
        JsonArray outcomes=view.getAsJsonArray("criteria");require(outcomes.size()==4,"One outcome per criterion id");
        Map<String,String> status=new LinkedHashMap<>();for(JsonElement item:outcomes)status.put(item.getAsJsonObject().get("id").getAsString(),item.getAsJsonObject().get("status").getAsString());
        require(status.equals(Map.of("fixed_passage","satisfied","frame_state","failed","continuable","indeterminate","record_reliability","not_verified")),"Worst status per criterion: "+status);
        JsonArray faults=view.getAsJsonArray("faults");require(faults.size()==2,"Mandatory unsatisfied rows are faults");
        JsonObject fault=faults.get(0).getAsJsonObject();require(fault.get("id").getAsString().equals("frame_state")&&fault.get("boundary").getAsString().equals("open")&&fault.get("mode").getAsString().equals("repeater")&&fault.has("expected")&&fault.has("observed")&&fault.get("diagnostic").getAsString().equals("diagnostic frame_state"),"A fault says where and why");
        JsonObject shownMeasurements=view.getAsJsonObject("measurements"),volume=shownMeasurements.getAsJsonObject("dynamic_volume"),opening=shownMeasurements.getAsJsonArray("transitions").get(0).getAsJsonObject().getAsJsonObject("opening_time");
        require(volume.get("status").getAsString().equals("indeterminate")&&volume.get("value").isJsonNull()&&volume.getAsJsonArray("gaps").size()==1,"Indeterminate volume keeps its gap");
        for(String key:List.of("sources","movements","excluded","conditional_roles"))require(!volume.has(key)&&!opening.has(key),key+" stays local");
        require(opening.get("value").getAsInt()==6,"Opening time kept");
        JsonObject shown=view.getAsJsonArray("boundaries").get(0).getAsJsonObject();
        require(shown.get("ticks_executed").getAsInt()==7&&shown.getAsJsonObject("rest").get("recognition_tick").getAsInt()==7&&!shown.getAsJsonObject("rest").has("rest_scope")&&!shown.has("geometry")&&!shown.has("operation")&&!shown.has("criteria"),"Boundary keeps its rest, not its raw operation or geometry");
        JsonObject snapshot=Artifacts.read(arguments(shown.getAsJsonObject("snapshot").get("artifact_id").getAsString()));
        require(snapshot.getAsJsonArray("entries").get(0).getAsJsonObject().get("world_time").getAsInt()==35,"Boundary snapshot artifact stays readable");
        require(full.getAsJsonArray("criteria").get(0).getAsJsonObject().has("sources")&&full.getAsJsonObject("measurements").getAsJsonObject("dynamic_volume").has("sources"),"The report passed in is not altered");

        // The same fault over several cycles is one entry; evidence already at the root is not repeated.
        JsonObject cycles=full.deepCopy();JsonArray more=cycles.getAsJsonArray("criteria");
        more.add(row("continuable","indeterminate",true,"repeater",2,"closed",JsonNull.INSTANCE));
        JsonArray comparisons=JsonParser.parseString("[{\"cycle\":1,\"equal\":false}]").getAsJsonArray();cycles.add("recurrence_comparisons",comparisons);
        JsonObject recurrence=row("fixed_passage","failed",true,"repeater",1,"closed",comparisons.deepCopy());recurrence.addProperty("id","recurrence");more.add(recurrence);
        JsonObject grouped=Verification.agentReport(cycles);JsonArray listed=grouped.getAsJsonArray("faults");
        require(listed.size()==3,"One fault per id/mode/boundary: "+listed);
        JsonObject repeated=listed.get(1).getAsJsonObject();require(repeated.get("id").getAsString().equals("continuable")&&repeated.getAsJsonArray("cycles").toString().equals("[1,2]")&&!repeated.has("cycle"),"Cycles are listed once: "+repeated);
        require(listed.get(2).getAsJsonObject().get("id").getAsString().equals("recurrence")&&!listed.get(2).getAsJsonObject().has("observed"),"Evidence shown at the root is not repeated");

        // A visible.json written before the concise form is rebuilt from the local report, never served.
        String id=UUID.randomUUID().toString();java.nio.file.Path directory=java.nio.file.Path.of("stonebench","verifications",id);
        try {
            java.nio.file.Files.createDirectories(directory);
            JsonObject legacy=new JsonObject();legacy.add("full_report",new JsonObject());legacy.add("criteria",full.getAsJsonArray("criteria").deepCopy());
            CheckpointStorage.writeAtomic(directory.resolve("visible.json"),legacy);
            JsonObject request=new JsonObject();request.addProperty("request_id",id);
            boolean refused=false;try{Verification.status(request);}catch(IllegalArgumentException expected){refused=true;}require(refused,"A legacy answer without its local report is refused");
            CheckpointStorage.writeAtomic(directory.resolve("completed.json"),full);
            JsonObject served=Verification.status(request).getAsJsonObject("verification");
            GeometryChecks.noSources(served,"legacy visible.json");require(!served.has("full_report")&&served.has("faults")&&served.get("verdict").getAsString().equals("failed"),"The legacy answer is rebuilt concise");
            require(CheckpointStorage.read(directory.resolve("visible.json")).has("faults"),"The rebuilt answer replaces the legacy file");
        } catch(java.io.IOException error){throw new AssertionError(error);}

        // Incomplete attempts: an infrastructure fallback has no criteria, boundaries or measurements.
        JsonObject lost=new JsonObject();lost.addProperty("request_id","r");lost.addProperty("verdict","infrastructure_error");lost.addProperty("conforms_to_alpha",false);lost.addProperty("stop_cause","owner_heartbeat_lost");lost.addProperty("infrastructure_error","Supervisor heartbeat absent");lost.addProperty("status","completed");
        JsonObject incomplete=Verification.agentReport(lost);GeometryChecks.noSources(incomplete,"incomplete");
        require(incomplete.get("verdict").getAsString().equals("infrastructure_error")&&incomplete.getAsJsonArray("criteria").isEmpty()&&incomplete.getAsJsonArray("faults").isEmpty()&&incomplete.getAsJsonArray("boundaries").isEmpty()&&!incomplete.has("measurements")&&incomplete.has("infrastructure_error"),"Fallback result keeps verdict and cause");
        System.out.println("VerificationChecks passed: concise report, outcomes, faults, evidence omission, incomplete attempts");
    }
}
