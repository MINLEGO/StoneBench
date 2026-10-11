package stonebench;

import com.google.gson.*;
import java.util.*;

/** One bounded transition, called only after complete real end-of-tick observations. */
public final class Transition {
    public static final long PROCESS_TIMEOUT_SECONDS=2400;
    private final int maximum;
    private final Rest rest;
    private JsonObject outcome;
    private int observedTicks,pendingTicks,movingTicks,quietPendingTicks;
    public Transition(JsonObject initial,int maximum,Set<String> externalInputPositions) {
        if(maximum<1 || maximum>Rest.MAX_TICKS) throw new IllegalArgumentException("max_ticks must be within 1..36000");
        this.maximum=maximum;rest=new Rest(initial,externalInputPositions);
    }
    public boolean tick(JsonObject raw,List<JsonObject> events,int executed) {
        if(outcome!=null && !outcome.get("status").getAsString().equals("running")) throw new IllegalStateException("Transition already finished");
        outcome=rest.accept(raw,events,executed,maximum);
        observedTicks++;boolean pending=false,moving=false;
        for(JsonElement value:outcome.getAsJsonArray("causes")) {String cause=value.getAsString();pending|=cause.startsWith("pending_");moving|=cause.equals("moving_piston");}
        if(pending) {pendingTicks++;if(outcome.get("states_equal").getAsBoolean()) quietPendingTicks++;}
        if(moving) movingTicks++;
        return !outcome.get("status").getAsString().equals("running");
    }
    public JsonObject report() {
        JsonObject result=outcome==null?new JsonObject():outcome.deepCopy();
        result.addProperty("observed_ticks",observedTicks);result.addProperty("pending_ticks",pendingTicks);result.addProperty("moving_ticks",movingTicks);result.addProperty("quiet_with_pending_ticks",quietPendingTicks);
        result.addProperty("maximum_ticks",maximum);result.addProperty("process_timeout_seconds",PROCESS_TIMEOUT_SECONDS);
        result.addProperty("tick_limit_kind","simulation");return result;
    }
}

