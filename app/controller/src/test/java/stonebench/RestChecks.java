package stonebench;

import com.google.gson.*;
import java.util.*;

/** Negative controls for classifier logic only; real simulation is tested through MCP separately. */
public final class RestChecks {
    private static JsonObject state() {
        return JsonParser.parseString("{\"blocks\":{},\"block_ticks\":[],\"fluid_ticks\":[],\"block_events\":[],\"coverage\":{\"status\":\"observed\",\"chunks_ready\":true}}").getAsJsonObject();
    }
    private static void status(String expected,JsonObject actual) {if(!expected.equals(actual.get("status").getAsString())) throw new AssertionError(actual);}
    public static void main(String[] args) {
        JsonObject initial=state();status("terminated",new Rest(initial,Set.of()).accept(initial,List.of(),1,10));
        JsonObject deferred=state();deferred.getAsJsonArray("block_ticks").add(JsonParser.parseString("{\"trigger_tick\":99}"));
        Rest pending=new Rest(deferred,Set.of());status("running",pending.accept(deferred,List.of(),1,2));status("limit_reached",pending.accept(deferred,List.of(),2,2));
        JsonObject mobile=state();mobile.getAsJsonObject("blocks").add("0,0,0",JsonParser.parseString("{\"block\":\"minecraft:moving_piston\"}"));status("running",new Rest(mobile,Set.of()).accept(mobile,List.of(),1,10));
        JsonObject gap=state();gap.getAsJsonObject("coverage").addProperty("status","insufficient");status("indeterminate",new Rest(gap,Set.of()).accept(gap,List.of(),1,10));
        Rest lost=new Rest(gap,Set.of());status("indeterminate",lost.accept(state(),List.of(),1,10));
        JsonObject unknown=state();unknown.getAsJsonObject("blocks").add("0,0,0",JsonParser.parseString("{\"block\":\"minecraft:furnace\",\"block_entity_type\":\"minecraft:furnace\"}"));status("indeterminate",new Rest(unknown,Set.of()).accept(unknown,List.of(),1,10));
        for(String enabled:List.of("true","false")) {
            JsonObject hopper=state();hopper.getAsJsonObject("blocks").add("0,0,0",JsonParser.parseString("{\"block\":\"minecraft:hopper\",\"block_entity_type\":\"minecraft:hopper\",\"parameters\":{\"enabled\":\""+enabled+"\"},\"inventory\":[],\"runtime\":{\"last_tick_time\":\"9007199254740993\",\"transfer_cooldown\":0}}"));
            JsonObject copy=hopper.deepCopy();status("indeterminate",new Rest(hopper,Set.of()).accept(hopper,List.of(),1,10));if(!hopper.equals(copy)) throw new AssertionError("Internal memory altered");
        }
        JsonObject inventory=state();inventory.getAsJsonObject("blocks").add("0,0,0",JsonParser.parseString("{\"block\":\"minecraft:chest\",\"block_entity_type\":\"minecraft:chest\",\"inventory\":[{\"count\":7}],\"nbt\":{\"type\":4,\"value\":\"9007199254740993L\"}}"));
        JsonObject changed=inventory.deepCopy();changed.getAsJsonObject("blocks").getAsJsonObject("0,0,0").getAsJsonArray("inventory").get(0).getAsJsonObject().addProperty("count",8);
        JsonObject nbtChanged=inventory.deepCopy();nbtChanged.getAsJsonObject("blocks").getAsJsonObject("0,0,0").getAsJsonObject("nbt").addProperty("value","9007199254740994L");status("running",new Rest(inventory,Set.of()).accept(nbtChanged,List.of(),1,10));
        Rest exact=new Rest(inventory,Set.of());status("running",exact.accept(changed,List.of(),1,10));JsonObject finished=exact.accept(changed,List.of(),2,10);status("terminated",finished);if(finished.get("last_movement_tick").getAsInt()!=1 || finished.get("recognition_tick").getAsInt()!=2) throw new AssertionError(finished);
        JsonObject event=JsonParser.parseString("{\"kind\":\"scheduled_block_tick\",\"position\":{\"x\":1,\"y\":2,\"z\":3},\"detail\":{}}").getAsJsonObject();
        JsonObject external=new Rest(initial,Set.of("1,2,3")).accept(initial,List.of(event),1,10);status("running",external);if(external.get("external_input_events").getAsInt()!=1) throw new AssertionError(external);
        try {new Rest(initial,Set.of()).accept(initial,List.of(),2,10);throw new AssertionError("Skipped tick accepted");} catch(IllegalArgumentException expected) {}
        System.out.println("RestChecks passed: queues, piston, memory, exact inventories/NBT, external event, typed temporal fields and negative coverage");
    }
}

