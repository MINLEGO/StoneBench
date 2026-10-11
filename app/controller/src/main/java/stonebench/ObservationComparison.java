package stonebench;

import com.google.gson.*;
import java.util.*;

/** Exact fields and ordered lists; no timing, inventory or numeric-type normalization. */
public final class ObservationComparison {
    public static JsonArray fields(JsonElement before,JsonElement after) {JsonArray rows=new JsonArray();compare("$",before,after,rows);return rows;}
    private static void compare(String path,JsonElement a,JsonElement b,JsonArray rows) {
        if(Objects.equals(a,b)) return;
        if(a!=null && b!=null && a.isJsonObject() && b.isJsonObject()) {
            Set<String> keys=new TreeSet<>(a.getAsJsonObject().keySet());keys.addAll(b.getAsJsonObject().keySet());
            for(String key:keys) compare(path+"."+key,a.getAsJsonObject().get(key),b.getAsJsonObject().get(key),rows);
        } else if(a!=null && b!=null && a.isJsonArray() && b.isJsonArray()) {
            int n=Math.max(a.getAsJsonArray().size(),b.getAsJsonArray().size());
            for(int i=0;i<n;i++) compare(path+"["+i+"]",i<a.getAsJsonArray().size()?a.getAsJsonArray().get(i):null,i<b.getAsJsonArray().size()?b.getAsJsonArray().get(i):null,rows);
        } else {
            JsonObject row=new JsonObject();row.addProperty("field",path);row.addProperty("before_present",a!=null);row.addProperty("after_present",b!=null);
            row.add("before",a==null?JsonNull.INSTANCE:a);row.add("after",b==null?JsonNull.INSTANCE:b);rows.add(row);
        }
    }
    public static JsonObject continuity(List<JsonObject> ticks,int expected,long startTime,long startIndex) {
        JsonObject result=new JsonObject();JsonArray problems=new JsonArray();
        if(ticks.size()!=expected) problems.add("expected "+expected+" end-of-tick observations, got "+ticks.size());
        for(int i=0;i<ticks.size();i++) {
            JsonObject tick=ticks.get(i);
            if(!valid(tick,i+1,startIndex+i+1,startTime+i+1)) problems.add("incomplete or discontinuous observation "+(i+1));
        }
        result.addProperty("complete",problems.isEmpty());result.addProperty("expected",expected);result.addProperty("observed",ticks.size());result.add("problems",problems);return result;
    }
    private static boolean valid(JsonObject tick,long index,long simulation,long time) {
        try {
            if(!number(tick.get("tick_index"),index) || !number(tick.get("simulation_index"),simulation) || !number(tick.get("world_time"),time)
                || !tick.get("complete").isJsonPrimitive() || !tick.get("complete").getAsJsonPrimitive().isBoolean() || !tick.get("complete").getAsBoolean()
                || !tick.get("phase").getAsString().equals("end_tick")) return false;
            JsonObject state=tick.getAsJsonObject("state");
            return (state.get("blocks").isJsonObject() || state.get("blocks").isJsonArray()) && state.get("block_ticks").isJsonArray() && state.get("fluid_ticks").isJsonArray()
                && state.get("block_events").isJsonArray() && state.get("coverage").isJsonObject() && (tick.get("events").isJsonObject() || tick.get("events").isJsonArray());
        } catch(RuntimeException e) {return false;}
    }
    private static boolean number(JsonElement value,long expected) {
        return value!=null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isNumber() && new java.math.BigDecimal(value.getAsString()).longValueExact()==expected;
    }
    public static JsonObject firstDivergence(List<JsonObject> a,List<JsonObject> b,int expected,long startTime,long startIndex) {
        JsonObject result=new JsonObject();result.add("left_continuity",continuity(a,expected,startTime,startIndex));result.add("right_continuity",continuity(b,expected,startTime,startIndex));
        boolean complete=result.getAsJsonObject("left_continuity").get("complete").getAsBoolean() && result.getAsJsonObject("right_continuity").get("complete").getAsBoolean();
        for(int i=0;i<Math.min(a.size(),b.size());i++) {JsonArray fields=fields(a.get(i),b.get(i));if(!fields.isEmpty()) {result.addProperty("status","different");result.addProperty("first_tick",i+1);result.add("first_fields",fields);return result;}}
        if(a.size()!=b.size()) {int i=Math.min(a.size(),b.size());result.addProperty("status","different");result.addProperty("first_tick",i+1);result.add("first_fields",fields(i<a.size()?a.get(i):null,i<b.size()?b.get(i):null));return result;}
        result.addProperty("status",complete?"equal":"incomplete");return result;
    }
}
