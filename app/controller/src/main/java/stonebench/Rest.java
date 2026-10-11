package stonebench;

import com.google.gson.*;
import java.util.*;
import java.util.function.Predicate;
import java.util.function.BiPredicate;

/** Conservative observed rest for Minecraft 1.21.11; not a conformity certificate. */
public final class Rest {
    public static final int MAX_TICKS=36000;
    private JsonObject previous;
    private int lastMovement, elapsed;
    private long internalEvents, externalEvents;
    private boolean coverageLost;
    private final Set<String> externalPositions;
    private final BiPredicate<JsonObject,JsonObject> expectedExternalEvent;

    public Rest(JsonObject initial,Set<String> externalPositions) {this(initial,externalPositions,event->false);}
    public Rest(JsonObject initial,Set<String> externalPositions,Predicate<JsonObject> expectedExternalEvent) {this(initial,externalPositions,(event,state)->expectedExternalEvent.test(event));}
    public Rest(JsonObject initial,Set<String> externalPositions,BiPredicate<JsonObject,JsonObject> expectedExternalEvent) {
        previous=initial.deepCopy();this.externalPositions=Set.copyOf(externalPositions);this.expectedExternalEvent=expectedExternalEvent;
        coverageLost=!complete(initial);
    }
    public JsonObject accept(JsonObject current,List<JsonObject> events,int tick,int maximum) {
        if(maximum<1 || maximum>MAX_TICKS || tick!=elapsed+1 || tick>maximum) throw new IllegalArgumentException("Transition observations must be consecutive real ticks within 1..36000");
        elapsed=tick;
        boolean changed=false;
        if(previous.has("blocks") && current.has("blocks")) {
            Set<String> positions=new HashSet<>(previous.getAsJsonObject("blocks").keySet());positions.addAll(current.getAsJsonObject("blocks").keySet());
            for(String position:positions) if(!externalPositions.contains(position) && !Objects.equals(previous.getAsJsonObject("blocks").get(position),current.getAsJsonObject("blocks").get(position))) changed=true;
        }
        boolean activity=false;
        for(JsonObject event:events) {
            String kind=event.get("kind").getAsString();
            if(kind.equals("block_state_read")) continue;
            if(kind.equals("block_write_result") && !event.getAsJsonObject("detail").get("changed").getAsBoolean()) continue;
            if(kind.equals("block_write_requested")) continue; // Actual result and neighbor/events retain effective activity.
            boolean callback=Set.of("scheduled_block_tick","block_tick_schedule_requested","block_event_callback","block_event_enqueued","scheduled_fluid_tick","fluid_tick_schedule_requested").contains(kind);
            boolean external=callback?expectedExternalEvent.test(event,current):externalPositions.contains(position(event.getAsJsonObject("position")));
            if(external) externalEvents++;else internalEvents++;
            // External callbacks still prevent a false pause; their future queue is never excluded.
            activity=true;
            if(!external && kind.equals("block_write_result")) changed=true;
        }
        if(changed) lastMovement=tick;
        JsonArray causes=new JsonArray();
        JsonObject coverage=current.getAsJsonObject("coverage");
        boolean insufficient=coverageLost || coverage==null || !coverage.has("status") || !coverage.get("status").getAsString().equals("observed") || !coverage.has("chunks_ready") || !coverage.get("chunks_ready").getAsBoolean();
        if(insufficient) causes.add("insufficient_observation_coverage");
        boolean pending=false,mobile=false,cooldown=false,transfer=false,hopper=false,unknown=false;
        for(String queue:List.of("block_ticks","fluid_ticks","block_events")) {
            if(!current.has(queue) || !current.get(queue).isJsonArray()) {insufficient=true;causes.add("missing_"+queue);}
            else if(!current.getAsJsonArray(queue).isEmpty()) {pending=true;causes.add("pending_"+queue);}
        }
        JsonObject blocks=current.getAsJsonObject("blocks");
        if(blocks==null) {insufficient=true;causes.add("missing_blocks");}
        else for(var item:blocks.entrySet()) {
            JsonObject block=item.getValue().getAsJsonObject();
            String id=block.get("block").getAsString();
            String entity=block.has("block_entity_type")?block.get("block_entity_type").getAsString():"";
            if(id.equals("minecraft:moving_piston") || entity.equals("minecraft:piston")) mobile=true;
            if(entity.equals("minecraft:hopper") || id.equals("minecraft:hopper")) {
                hopper=true;
                JsonObject runtime=block.getAsJsonObject("runtime");
                if(runtime==null || !runtime.has("last_tick_time") || !runtime.has("transfer_cooldown")) {insufficient=true;causes.add("missing_hopper_runtime:"+item.getKey());}
                else cooldown|=runtime.get("transfer_cooldown").getAsInt()>0;
                transfer|=block.getAsJsonObject("parameters").get("enabled").getAsString().equals("true") && !block.getAsJsonArray("inventory").isEmpty();
            } else if(!entity.isEmpty() && !Set.of("minecraft:chest","minecraft:piston").contains(entity)) {
                unknown=true;causes.add("unestablished_runtime_memory:"+item.getKey()+":"+entity);
            }
        }
        if(mobile) causes.add("moving_piston");
        if(cooldown) causes.add("hopper_cooldown");
        if(transfer) causes.add("hopper_transfer_possible");
        if(hopper) causes.add("hopper_last_tick_time_effect_and_resume_unestablished");
        boolean same=Objects.equals(previous.get("blocks"),current.get("blocks"));
        if(!same) causes.add("relevant_state_changed");
        if(activity) causes.add("relevant_events_this_tick");
        coverageLost|=insufficient;
        String status="running";
        if(insufficient) status="indeterminate";
        else if(!pending && !mobile && !cooldown && !transfer && (hopper || unknown)) status="indeterminate";
        else if(!pending && !mobile && !cooldown && !transfer && same && !activity) status="terminated";
        else if(tick==maximum) status="limit_reached";
        if(status.equals("terminated")) causes.add("quiescent_two_consecutive_states");
        String cause=status.equals("terminated")?"quiescent_two_consecutive_states":status.equals("limit_reached")?"simulation_tick_limit":insufficient?"insufficient_observation_coverage":status.equals("indeterminate") && hopper?"hopper_last_tick_time_effect_and_resume_unestablished":status.equals("indeterminate")?"unestablished_runtime_memory":causes.isEmpty()?"awaiting_consecutive_state":causes.get(0).getAsString();
        JsonObject result=new JsonObject();result.addProperty("status",status);result.addProperty("cause",cause);result.addProperty("tick",tick);result.addProperty("last_movement_tick",lastMovement);
        result.add("recognition_tick",status.equals("terminated")?new JsonPrimitive(tick):JsonNull.INSTANCE);
        result.addProperty("states_equal",same);result.addProperty("internal_events",internalEvents);result.addProperty("external_input_events",externalEvents);result.add("causes",causes);
        result.addProperty("rest_scope","Observed influence and covered prototype components only; not universal memory, restoration or door conformity");
        previous=current.deepCopy();return result;
    }
    private static boolean complete(JsonObject state) {
        try {
            JsonObject coverage=state.getAsJsonObject("coverage");
            if(!coverage.get("status").getAsString().equals("observed") || !coverage.get("chunks_ready").getAsBoolean() || !state.get("blocks").isJsonObject()) return false;
            for(String queue:List.of("block_ticks","fluid_ticks","block_events")) if(!state.get(queue).isJsonArray()) return false;
            return true;
        } catch(RuntimeException e) {return false;}
    }
    private static String position(JsonObject value) {return value.get("x").getAsInt()+","+value.get("y").getAsInt()+","+value.get("z").getAsInt();}
}
