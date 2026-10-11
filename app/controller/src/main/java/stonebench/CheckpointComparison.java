package stonebench;

import com.google.gson.*;

/** Exact pre-tick comparison; a matching incomplete observation never proves fidelity. */
public final class CheckpointComparison {
    private CheckpointComparison() {}

    public static JsonObject compare(JsonObject expected, JsonObject actual) {
        JsonArray fields=ObservationComparison.fields(expected,actual);
        boolean complete=complete(expected) && complete(actual);
        JsonObject result=new JsonObject();
        result.addProperty("status",fields.isEmpty()?(complete?"equal":"indeterminate"):"different");
        result.addProperty("first_tick",0);
        result.addProperty("phase","before_first_useful_tick");
        result.addProperty("complete",complete);
        result.add("first_fields",fields);
        result.addProperty("scope","Exact observed clocks, queues, typed NBT, inventories and runtime; not all JVM memory");
        return result;
    }

    static boolean complete(JsonObject snapshot) {
        try {
            snapshot.get("world_time").getAsLong();snapshot.get("time_of_day").getAsLong();
            JsonObject state=snapshot.getAsJsonObject("state"),coverage=state.getAsJsonObject("coverage");
            if(!coverage.get("status").getAsString().equals("observed") || !coverage.get("chunks_ready").getAsBoolean()) return false;
            if(!state.get("blocks").isJsonObject()) return false;
            for(String queue:java.util.List.of("block_ticks","fluid_ticks","block_events")) if(!state.get(queue).isJsonArray()) return false;
            return true;
        } catch(RuntimeException e) {return false;}
    }
}
