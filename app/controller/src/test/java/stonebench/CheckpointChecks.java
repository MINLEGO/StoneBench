package stonebench;

import com.google.gson.*;
import java.nio.file.*;
import java.io.IOException;
import java.util.*;

/** Pure negative controls supplement (never replace) the real checkpoint/replay MCP suite. */
public final class CheckpointChecks {
    private static void check(boolean value,String message) {if(!value) throw new AssertionError(message);}
    private static void rejected(Throwing action,String message) throws Exception {
        try {action.run();} catch(IllegalArgumentException|IllegalStateException|IOException expected) {return;}
        throw new AssertionError(message);
    }
    private interface Throwing {void run() throws Exception;}
    private static JsonObject json(String text) {return JsonParser.parseString(text).getAsJsonObject();}

    public static void main(String[] args) throws Exception {
        JsonObject state=json("""
            {"world_time":20,"time_of_day":20,"state":{"blocks":{"7,80,3":
            {"block":"minecraft:chest","block_entity_type":"minecraft:chest","inventory":[{"slot":0,"item":"minecraft:diamond","count":7}],
             "nbt":{"type":10,"value":{"Items":{"type":9,"value":[{"type":10,"value":{"count":{"type":3,"value":"7"}}}]}}}}},
             "block_ticks":[],"fluid_ticks":[],"block_events":[],"coverage":{"status":"observed","chunks_ready":true}}}
            """);
        JsonObject report=json("{\"status\":\"terminated\",\"recognition_tick\":1}");
        rejected(()->Checkpoints.requireRest(state,true),"Frozen does not establish rest");
        Checkpoints.recordRest(state,report);Checkpoints.requireRest(state,true);
        rejected(()->Checkpoints.requireRest(state,false),"Unfrozen checkpoint accepted");
        JsonObject changed=state.deepCopy();changed.addProperty("world_time",21);
        rejected(()->Checkpoints.requireRest(changed,true),"Stale rest proof accepted");
        JsonObject hopper=state.deepCopy();hopper.getAsJsonObject("state").getAsJsonObject("blocks").add("8,80,3",json("{\"block\":\"minecraft:hopper\",\"block_entity_type\":\"minecraft:hopper\"}"));
        Checkpoints.recordRest(hopper,report);rejected(()->Checkpoints.requireRest(hopper,true),"Unestablished hopper memory accepted");
        JsonObject torch=state.deepCopy();torch.getAsJsonObject("state").getAsJsonObject("blocks").add("8,80,3",json("{\"block\":\"minecraft:redstone_torch\"}"));
        Checkpoints.recordRest(torch,report);rejected(()->Checkpoints.requireRest(torch,true),"Torch burnout memory accepted");
        JsonObject pending=state.deepCopy();pending.getAsJsonObject("state").getAsJsonArray("block_ticks").add(json("{\"trigger_tick\":80}"));
        Checkpoints.recordRest(pending,report);rejected(()->Checkpoints.requireRest(pending,true),"Pending events accepted");
        Checkpoints.recordRest(state,json("{\"status\":\"indeterminate\"}"));rejected(()->Checkpoints.requireRest(state,true),"Indeterminate rest accepted");

        JsonObject negative=state.deepCopy();
        negative.getAsJsonObject("state").getAsJsonObject("blocks").getAsJsonObject("7,80,3").getAsJsonObject("nbt").getAsJsonObject("value").getAsJsonObject("Items").getAsJsonArray("value").get(0).getAsJsonObject().getAsJsonObject("value").getAsJsonObject("count").addProperty("value","8");
        JsonObject difference=CheckpointComparison.compare(state,negative);
        check(difference.get("status").getAsString().equals("different"),"7 -> 8 accepted");
        check(difference.get("first_tick").getAsInt()==0,"Wrong divergence tick");
        check(difference.getAsJsonArray("first_fields").get(0).getAsJsonObject().get("field").getAsString().equals("$.state.blocks.7,80,3.nbt.value.Items.value[0].value.count.value"),"Inventory NBT field not exact");
        negative=state.deepCopy();negative.getAsJsonObject("state").getAsJsonObject("blocks").getAsJsonObject("7,80,3").getAsJsonObject("nbt").addProperty("type",9);
        check(CheckpointComparison.compare(state,negative).get("status").getAsString().equals("different"),"NBT type lost");
        check(CheckpointComparison.compare(state,changed).get("status").getAsString().equals("different"),"Clock normalization");
        JsonObject incomplete=state.deepCopy();incomplete.getAsJsonObject("state").getAsJsonObject("coverage").addProperty("status","insufficient");
        check(CheckpointComparison.compare(incomplete,incomplete).get("status").getAsString().equals("indeterminate"),"Incomplete equality accepted");

        Path temporary=Files.createTempDirectory("stonebench-checkpoint-checks-");
        try {
            Path world=temporary.resolve("live-world"),store=temporary.resolve("checkpoints"),server=temporary.resolve("server");
            Files.createDirectories(world.resolve("region"));Files.createDirectories(server.resolve("stonebench"));
            Files.writeString(world.resolve("level.dat"),"exact clocks");Files.writeString(world.resolve("region/r.0.0.mca"),"seven diamonds");
            Files.writeString(world.resolve("session.lock"),"not construction state");
            CheckpointStorage storage=new CheckpointStorage(store);
            String attempt=UUID.randomUUID().toString();JsonObject context=json("{\"attempt_id\":\""+attempt+"\"}");
            JsonObject first=storage.create(world,context,state,new JsonObject());String id=first.get("checkpoint_id").getAsString();
            JsonObject second=storage.create(world,context,state,new JsonObject());
            check(storage.list().size()==2,"Multiple checkpoint IDs lost");
            check(!id.equals(second.get("checkpoint_id").getAsString()),"ID reused");
            check(!Files.exists(store.resolve(id).resolve("world/session.lock")),"Process lock copied");
            check(storage.state(id).equals(state),"Exact saved snapshot changed");
            check(first.equals(storage.descriptor(id)),"Listing changed immutable metadata");
            rejected(()->storage.requestRestore(id,server,UUID.randomUUID().toString()),"Other attempt checkpoint restored");
            storage.requestRestore(id,server,attempt);check(storage.list().size()==2,"Restore request removed other checkpoints");
            rejected(()->storage.requestRestore(id,server,attempt),"Duplicate restore request accepted");
            rejected(()->storage.descriptor("../escape"),"Unsafe checkpoint path accepted");
            Files.writeString(store.resolve(id).resolve("world/region/r.0.0.mca"),"eight diamonds");
            rejected(()->storage.descriptor(id),"Corrupt immutable world accepted");
            check(storage.descriptor(second.get("checkpoint_id").getAsString()).get("verified").getAsBoolean(),"Corruption lost another checkpoint");
        } finally {
            try(var paths=Files.walk(temporary)) {for(Path path:paths.sorted(Comparator.reverseOrder()).toList()) Files.delete(path);}
        }
        System.out.println("CheckpointChecks: exact tick0 fields/types/clocks, stale/unknown rest and immutable storage negative controls passed");
    }
}
