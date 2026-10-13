package stonebench;

import com.google.gson.*;
import java.util.*;

/** Source-table-driven negative controls for geometry interpretation, not Minecraft validation. */
public final class GeometryChecks {
    static void require(boolean ok,String message){if(!ok)throw new AssertionError(message);}
    static String status(JsonObject report,String id){for(JsonElement row:report.getAsJsonArray("criteria"))if(row.getAsJsonObject().get("id").getAsString().equals(id))return row.getAsJsonObject().get("status").getAsString();throw new AssertionError(id);}
    static List<RegularDoorGeometry.Cell> fixture(boolean closed,int depth){List<RegularDoorGeometry.Cell> cells=new ArrayList<>();for(int z=1024;z<1024+depth;z++)for(int y=79;y<=82;y++)for(int x=1023;x<=1026;x++){boolean filled=closed||x==1023||x==1026||y==79||y==82;cells.add(new RegularDoorGeometry.Cell(x,y,z,filled?"minecraft:quartz_block":"minecraft:air",filled,filled,filled));}return cells;}
    static JsonObject check(boolean closed,List<RegularDoorGeometry.Cell> cells){JsonObject args=new JsonObject();args.addProperty("expected_state",closed?"closed":"open");JsonObject coverage=new JsonObject();coverage.addProperty("status","observed");coverage.addProperty("chunks_ready",true);coverage.addProperty("certification",false);return RegularDoorGeometry.evaluate(Task.describe("2x2-volume",null),args,cells,coverage,null,new JsonArray());}
    /** Agent-facing text may carry neither documents nor citation metadata; verdicts and diagnostics are those of the full rows. */
    static void noSources(JsonElement value,String path){
        if(value.isJsonObject())for(var entry:value.getAsJsonObject().entrySet()){
            require(!Set.of("source","sources","revision_id","source_index","locator","locator_type","authority","native_cache_sha256","rules_reference").contains(entry.getKey())&&!entry.getKey().contains("source_index"),"Citation key "+path+"."+entry.getKey());noSources(entry.getValue(),path+"."+entry.getKey());}
        else if(value.isJsonArray())for(JsonElement item:value.getAsJsonArray())noSources(item,path+"[]");
        else if(value.isJsonPrimitive()&&value.getAsJsonPrimitive().isString())for(String marker:List.of("docs.google.com","github.com","sha256","index ","Dummies"))require(!value.getAsString().contains(marker),"Citation text "+path+": "+value.getAsString());
    }
    static void presentation(JsonObject closed,JsonObject open){
        JsonObject full=Rules.describe(),agent=Rules.agentRules(full);noSources(agent,"describe_rules");
        require(full.getAsJsonArray("criteria").size()==16&&agent.getAsJsonArray("criteria").size()==14,"Three community criteria become one summary");
        for(JsonElement item:agent.getAsJsonArray("criteria")){JsonObject row=item.getAsJsonObject();require(row.has("expected")&&row.has("observation")&&row.has("coverage")&&row.has("mandatory"),"Agent criterion keeps behavior, scope, limits and mandatory status: "+row);}
        require(!agent.getAsJsonArray("criteria").get(13).getAsJsonObject().get("mandatory").getAsBoolean()&&agent.getAsJsonArray("criteria").get(13).getAsJsonObject().get("id").getAsString().equals("record_eligibility"),"Outside-alpha summary");
        JsonObject contract=agent.getAsJsonObject("measurement_contract");for(String key:List.of("volume","exclusions","opening_end","closing_end","movement_end","timing_origin","rest"))require(contract.has(key),"Measurement definition "+key);
        require(JsonParser.parseString(full.toString()).getAsJsonObject().getAsJsonArray("criteria").get(0).getAsJsonObject().has("sources"),"The audit form keeps its sources");
        require(agent.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8).length<8192,"describe_rules payload leaves ample margin below 16 KiB: "+agent.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8).length);
        for(JsonObject report:List.of(closed,open)){
            JsonObject view=Rules.agentGeometry(report);noSources(view,"check_geometry");
            for(String key:List.of("geometry_status","conforms_to_alpha","measurement_roles","coverage"))require(view.get(key).equals(report.get(key)),"Unchanged "+key);
            for(JsonElement item:view.getAsJsonArray("criteria")){JsonObject row=item.getAsJsonObject();require(row.has("status")&&row.has("observed")&&row.has("diagnostic")&&row.has("expected"),"Diagnostic keeps status, explanation and observed evidence: "+row);require(row.get("status").getAsString().equals(row.get("id").getAsString().equals("record_eligibility")?"not_verified":status(report,row.get("id").getAsString())),"Status unchanged "+row.get("id"));}
        }
    }
    public static void main(String[] args){
        JsonObject closed=check(true,fixture(true,1)),open=check(false,fixture(false,1));
        require(status(closed,"frame_state").equals("satisfied"),"Principal 30358 all frame cells closed");require(status(open,"frame_state").equals("satisfied"),"Principal 30358 frame opened");require(status(closed,"door_composition").equals("satisfied"),"Principal 31749 canonical quartz identity replacement");
        require(status(closed,"encadrement").equals("satisfied"),"Dummies 9641 physical frame layer");require(status(open,"continuable").equals("satisfied"),"Principal 14017, Dummies 5274 clear fixed rays");
        require(status(open,"stable_state").equals("indeterminate"),"Frozen state is not stability proof");require(status(open,"influence_coverage").equals("indeterminate"),"Snapshot is not transient proof");require(!open.get("conforms_to_alpha").getAsBoolean(),"No protocol certification from snapshot");
        require(status(closed,"regular_arrangement").equals("satisfied"),"Closed rectangular occupation");require(status(open,"regular_arrangement").equals("indeterminate"),"Open cannot prove closed arrangement");require(status(check(true,fixture(false,1)),"regular_arrangement").equals("failed"),"Air cannot be closed arrangement");
        List<RegularDoorGeometry.Cell> obstruction=fixture(false,1);obstruction.add(new RegularDoorGeometry.Cell(1024,80,1030,"minecraft:stone",true,true,true));JsonObject blocked=check(false,obstruction);require(status(blocked,"continuable").equals("failed"),"Off-plane obstruction must not move passage");
        List<RegularDoorGeometry.Cell> displaced=fixture(true,1);displaced.removeIf(c->c.x()==1023);require(status(check(true,displaced),"encadrement").equals("indeterminate"),"Missing observation cannot masquerade as empty-world failure");
        List<RegularDoorGeometry.Cell> airRing=fixture(true,1);airRing.removeIf(c->c.x()==1023&&c.y()==80);airRing.add(new RegularDoorGeometry.Cell(1023,80,1024,"minecraft:air",false,false,false));require(status(check(true,airRing),"encadrement").equals("failed"),"Observed missing encadrement fails");
        List<RegularDoorGeometry.Cell> stone=fixture(true,1);stone.removeIf(c->c.x()==1024&&c.y()==80);stone.add(new RegularDoorGeometry.Cell(1024,80,1024,"minecraft:stone",true,true,true));require(status(check(true,stone),"door_composition").equals("indeterminate"),"Physical properties alone do not prove substitution functionality");
        JsonObject task=Task.describe("2x2-volume",null),request=new JsonObject();request.addProperty("expected_state","closed");request.addProperty("frame_min_z",1024);request.addProperty("frame_max_z",1025);require(RegularDoorGeometry.requiredPositions(task,request).size()==32,"Dummies 9641 layer(s), no universal single-block depth");
        request.addProperty("frame_min_z",1025);try{RegularDoorGeometry.requiredPositions(task,request);throw new AssertionError("Shift accepted");}catch(IllegalArgumentException expected){}
        for(JsonElement row:Rules.describe().getAsJsonArray("criteria")){JsonObject c=row.getAsJsonObject();require(c.has("sources")&&c.has("expected")&&c.has("observation")&&c.has("coverage"),"Table completeness");}
        presentation(closed,open);
        System.out.println("GeometryChecks: source interpretation and negative controls passed; Minecraft/MCP not exercised.");
    }
}
