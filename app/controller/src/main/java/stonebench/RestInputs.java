package stonebench;

import com.google.gson.*;
import java.util.*;
import net.minecraft.util.math.BlockPos;

/** Classifies expected adapter callbacks from the captured real state; excludes no future work. */
final class RestInputs {
    static Set<String> positions() {
        Set<String> result=new HashSet<>();JsonObject declared=Inputs.declared();if(declared==null) return result;
        for(JsonElement value:declared.getAsJsonArray("adapter_positions")) result.add(key(value.getAsJsonObject()));return result;
    }
    static boolean expected(JsonObject event,JsonObject raw) {
        String kind=event.get("kind").getAsString();if(!Set.of("scheduled_block_tick","block_tick_schedule_requested").contains(kind)) return false;
        JsonObject p=event.getAsJsonObject("position"),declared=Inputs.declared();if(declared==null) return false;
        BlockPos pos=new BlockPos(p.get("x").getAsInt(),p.get("y").getAsInt(),p.get("z").getAsInt());if(!Inputs.expectedExternalEvent(pos)) return false;
        JsonObject row=raw.getAsJsonObject("blocks").getAsJsonObject(key(p));if(row==null) return false;
        String actual=row.get("block").getAsString();JsonObject parameters=row.getAsJsonObject("parameters"),detail=event.getAsJsonObject("detail");
        String expected=detail.get(kind.equals("scheduled_block_tick")?"block":"type").getAsString();
        if(!actual.equals(expected) || !parameters.has("facing") || !parameters.get("facing").getAsString().equals(declared.get("orientation").getAsString())) return false;
        if(p.equals(declared.getAsJsonObject("driver"))) return actual.equals(declared.get("device").getAsString()) && actual.endsWith("_button") && parameters.has("face") && parameters.get("face").getAsString().equals("wall");
        return declared.get("mode").getAsString().equals("repeater") && p.equals(declared.getAsJsonObject("position")) && actual.equals("minecraft:repeater") && parameters.get("delay").getAsString().equals("1");
    }
    private static String key(JsonObject p) {return p.get("x").getAsInt()+","+p.get("y").getAsInt()+","+p.get("z").getAsInt();}
}
