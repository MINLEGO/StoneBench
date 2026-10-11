package stonebench;
import com.google.gson.*;
import java.nio.file.*;
import java.util.*;
public final class InputComparisonChecks {
    public static void main(String[] args) throws Exception {
        JsonObject metadata=new JsonObject();metadata.addProperty("expected_ticks",1);metadata.addProperty("start_world_time",100);metadata.addProperty("start_simulation_index",10);
        JsonObject a=tick(7), b=tick(7);
        JsonObject left=Artifacts.write("trace",List.of(a),metadata), right=Artifacts.write("trace",List.of(b),metadata);
        check(TraceComparison.compare(left.get("artifact_id").getAsString(),right.get("artifact_id").getAsString()).get("status").getAsString().equals("equal"),"equal nested partitions with different IDs");
        JsonObject changed=Artifacts.write("trace",List.of(tick(8)),metadata);
        JsonObject diff=TraceComparison.compare(left.get("artifact_id").getAsString(),changed.get("artifact_id").getAsString());
        check(diff.get("status").getAsString().equals("different"),"changed construction partition detected");
        JsonObject page=new JsonObject();page.addProperty("artifact_id",diff.getAsJsonObject("first_fields").get("artifact_id").getAsString());page.addProperty("offset",0);page.addProperty("limit",256);
        check(Artifacts.read(page).getAsJsonArray("entries").asList().stream().anyMatch(e->e.getAsJsonObject().get("field").getAsString().equals("$.construction_blocks[0].count")),"exact partition field");
        String id=b.getAsJsonObject("adapter_blocks").get("artifact_id").getAsString();Files.writeString(Path.of("stonebench/artifacts/"+id+".jsonl"),"corrupted\n");
        boolean rejected=false;try {TraceComparison.compare(left.get("artifact_id").getAsString(),right.get("artifact_id").getAsString());} catch(IllegalStateException e) {rejected=true;}
        check(rejected,"partition corruption rejected after prior read");
        System.out.println("Input comparison checks passed");
    }
    private static JsonObject tick(int count) {
        JsonObject tick=new JsonObject();tick.addProperty("tick_index",1);tick.addProperty("simulation_index",11);tick.addProperty("world_time",101);tick.addProperty("time_of_day",101);tick.addProperty("phase","end_tick");tick.addProperty("complete",true);
        JsonObject state=new JsonObject();state.add("blocks",Artifacts.write("snapshot_blocks",List.of()));for(String key:List.of("block_ticks","fluid_ticks","block_events")) state.add(key,new JsonArray());state.add("coverage",new JsonObject());tick.add("state",state);tick.add("events",Artifacts.write("intratick_events",List.of()));
        JsonObject row=new JsonObject();row.addProperty("count",count);tick.add("construction_blocks",Artifacts.write("input_construction_blocks",List.of(row)));tick.add("adapter_blocks",Artifacts.write("input_adapter_blocks",List.of(row)));return tick;
    }
    private static void check(boolean condition,String message) {if(!condition) throw new AssertionError(message);}
}

