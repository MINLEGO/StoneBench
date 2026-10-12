package stonebench;

import com.google.gson.*;
import com.sun.net.httpserver.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

/** Stateless MCP Streamable HTTP, JSON responses, no optional SSE/session features. */
public final class McpHttp implements AutoCloseable {
    private static final Gson JSON=new GsonBuilder().serializeNulls().disableHtmlEscaping().create();
    private static final Set<String> VERSIONS=Set.of("2025-11-25","2025-06-18","2025-03-26");
    private final HttpServer http;
    private final ExecutorService executor=Executors.newFixedThreadPool(8);
    McpHttp(int port) throws IOException {
        http=HttpServer.create(new InetSocketAddress("127.0.0.1",port),16);
        http.createContext("/mcp",this::handle);http.setExecutor(executor);http.start();
    }
    private void handle(HttpExchange exchange) throws IOException {
        String restoreResponseId=null;
        boolean responseWritten=false;
        try {
            String origin=exchange.getRequestHeaders().getFirst("Origin");
            if(origin!=null && !origin.equals("http://127.0.0.1:"+http.getAddress().getPort()) && !origin.equals("http://localhost:"+http.getAddress().getPort())) {send(exchange,403,null);return;}
            if(!exchange.getRequestURI().getPath().equals("/mcp")) {send(exchange,404,null);return;}
            if(!exchange.getRequestMethod().equals("POST")) {exchange.getResponseHeaders().set("Allow","POST");send(exchange,405,null);return;}
            String version=exchange.getRequestHeaders().getFirst("MCP-Protocol-Version");
            if(version!=null&&!VERSIONS.contains(version)) {send(exchange,400,null);return;}
            byte[] bytes=exchange.getRequestBody().readNBytes(65537);
            if(bytes.length>65536) {send(exchange,413,null);return;}
            JsonElement parsed;
            try {parsed=JsonParser.parseString(new String(bytes,StandardCharsets.UTF_8));}
            catch(JsonParseException e) {send(exchange,400,error(JsonNull.INSTANCE,-32700,"Parse error"));return;}
            if(!parsed.isJsonObject()) {send(exchange,400,error(JsonNull.INSTANCE,-32600,"Expected one JSON-RPC object"));return;}
            JsonObject request=parsed.getAsJsonObject();JsonElement id=request.has("id")?request.get("id"):JsonNull.INSTANCE;
            if(!request.has("jsonrpc")||!request.get("jsonrpc").getAsString().equals("2.0")||!request.has("method")||!request.get("method").isJsonPrimitive()) {send(exchange,400,error(id,-32600,"Invalid request"));return;}
            String method=request.get("method").getAsString();
            if(!request.has("id")) {send(exchange,202,null);return;}
            JsonObject params=request.has("params")&&request.get("params").isJsonObject()?request.getAsJsonObject("params"):new JsonObject();
            JsonObject result;
            switch(method) {
                case "initialize" -> {
                    result=new JsonObject();String wanted=params.has("protocolVersion")?params.get("protocolVersion").getAsString():"2025-11-25";
                    result.addProperty("protocolVersion",VERSIONS.contains(wanted)?wanted:"2025-11-25");
                    JsonObject capabilities=new JsonObject();capabilities.add("tools",new JsonObject());result.add("capabilities",capabilities);
                    JsonObject info=new JsonObject();info.addProperty("name","stonebench");info.addProperty("version","0.1.0");result.add("serverInfo",info);
                }
                case "ping" -> result=new JsonObject();
                case "tools/list" -> {result=new JsonObject();result.add("tools",tools());}
                case "tools/call" -> {
                    if(!params.has("name")||!params.get("name").isJsonPrimitive()||!params.get("name").getAsJsonPrimitive().isString()) {send(exchange,200,error(id,-32602,"Missing tool name"));return;}
                    String tool=params.get("name").getAsString();
                    if(!names().contains(tool)) {send(exchange,200,error(id,-32602,"Unknown tool"));return;}
                    if(params.has("arguments")&&!params.get("arguments").isJsonObject()) {send(exchange,200,error(id,-32602,"arguments must be an object"));return;}
                    JsonObject args=params.has("arguments")?params.getAsJsonObject("arguments"):new JsonObject();
                    // A disconnected client does not cancel an operation already accepted by Minecraft.
                    JsonObject report=Controller.submit(tool,args).get();
                    if(tool.equals("restore_checkpoint") && report.get("status").getAsString().equals("ok")) restoreResponseId=report.getAsJsonObject("restore").get("request_id").getAsString();
                    result=new JsonObject();result.add("structuredContent",report);result.addProperty("isError",report.get("status").getAsString().equals("error"));
                    JsonObject content=new JsonObject();content.addProperty("type","text");content.addProperty("text",JSON.toJson(report));JsonArray contents=new JsonArray();contents.add(content);result.add("content",contents);
                }
                default -> {send(exchange,200,error(id,-32601,"Method not found"));return;}
            }
            JsonObject response=new JsonObject();response.addProperty("jsonrpc","2.0");response.add("id",id);response.add("result",result);send(exchange,200,response);
            responseWritten=true;
        } catch(InterruptedException e) {Thread.currentThread().interrupt();send(exchange,503,null);}
        catch(ExecutionException e) {send(exchange,503,null);}
        catch(RuntimeException e) {send(exchange,400,error(JsonNull.INSTANCE,-32600,"Invalid request"));}
        finally {exchange.close();if(responseWritten && restoreResponseId!=null) Controller.restoreResponseSent(restoreResponseId);}
    }
    private static Set<String> names() {
        Set<String> names=new LinkedHashSet<>(List.of("start_attempt","describe_task","read_blocks","read_region","read_artifact","compare_traces","describe_blocks","modify_blocks","advance","transition","declare_input","prepare_input","act_input","describe_rules","check_geometry","create_checkpoint","list_checkpoints","restore_checkpoint","verify_checkpoint","verification_snapshot"));
        names.addAll(List.of("verification_status","cancel_verification"));
        if(Controller.TEST) names.addAll(List.of("__test_release_chunks","__test_restore_chunks","__test_place_block","__test_fail_next_lot","__test_default_wire","__test_outside_influence","__test_water_source","__test_transition_fixture","__test_transition_toggle","__test_transition_external_tick","__test_geometry_entity","__test_checkpoint_fixture","__test_checkpoint_toggle","__test_checkpoint_snapshot","__test_checkpoint_compare","__test_verification_fixture","__test_verification_config","__test_verification_mutate"));return names;
    }
    private static JsonObject property(String type) {JsonObject p=new JsonObject();p.addProperty("type",type);return p;}
    private static JsonObject integer(int min,int max) {JsonObject p=property("integer");p.addProperty("minimum",min);p.addProperty("maximum",max);return p;}
    private static JsonObject placementSchema() {
        JsonObject placement=property("object"),properties=new JsonObject();JsonArray required=new JsonArray();
        for(String coordinate:List.of("x","y","z")) {properties.add(coordinate,property("integer"));required.add(coordinate);}
        properties.add("block",property("string"));required.add("block");
        JsonObject parameters=property("object");parameters.add("additionalProperties",property("string"));properties.add("parameters",parameters);
        JsonObject inventory=property("array"),item=property("object"),itemProperties=new JsonObject();itemProperties.add("slot",integer(0,26));itemProperties.add("item",property("string"));itemProperties.add("count",integer(1,Integer.MAX_VALUE));item.add("properties",itemProperties);JsonArray itemRequired=new JsonArray();for(String key:List.of("slot","item","count")) itemRequired.add(key);item.add("required",itemRequired);item.addProperty("additionalProperties",false);inventory.add("items",item);properties.add("inventory",inventory);
        placement.add("properties",properties);placement.add("required",required);placement.addProperty("additionalProperties",false);return placement;
    }
    private static JsonArray tools() {
        JsonArray tools=new JsonArray();
        for(String name:names()) {
            JsonObject tool=new JsonObject(),schema=property("object"),properties=new JsonObject();JsonArray required=new JsonArray();
            tool.addProperty("name",name);tool.addProperty("description",switch(name) {
                case "verification_snapshot"->"Read complete raw state, construction partition, clocks and declared adapter without advancing time.";
                case "verification_status"->"Read an asynchronous verification job progress or immutable final report by request_id; no game ticks.";
                case "cancel_verification"->"Cancel an asynchronous job; the owning supervisor stops only its copy processes and preserves evidence.";
                case "verify_checkpoint"->"Start an independent-copy verification job and return request_id immediately; poll verification_status for the final report.";
                case "start_attempt"->"Initialize one fresh isolated regular DOOR attempt; budget in tokens is supplied by the caller.";
                case "describe_task"->"Describe immutable task, effective clock, environment and chunk readiness.";
                case "read_blocks"->"Read 1..256 actual block states in prepared chunks; larger reads must be split.";
                case "describe_rules"->"Read the frozen sourced regular DOOR criteria and measurement event/exclusion contract.";
                case "check_geometry"->"Observe fixed regular DOOR frame/passage, physical enclosure, continuation, material, input and entities without advancing time; unresolved functional/coverage criteria remain indeterminate.";
                case "describe_blocks"->"Discover explicit construction coverage, in-game configurable parameters, computed states and inventory slots.";
                case "modify_blocks"->"Validate an entire ordered lot, place all geometry/inventories with deferred callbacks then optionally notify in submitted order; errors report actual effects.";
                case "declare_input"->"Declare an existing inactive wall lever/button on a lateral exterior construction surface.";
                case "prepare_input"->"Prepare a real external vanilla repeater adapter while frozen; verify exact construction state preservation.";
                case "act_input"->"Interact with the declared vanilla device before world-time increment then execute 1..6000 ticks; buttons release naturally, lever toggles.";
                case "advance"->"Advance 1..6000 individual vanilla game ticks; initial/final diff is an artifact, optional trace contains one complete observation per executed tick. Read artifacts with explicit pages.";
                case "transition"->"Observe a transition until rest, indeterminate memory/coverage, or 1..36000 real ticks; process deadline is separate. Ordinary advance remains 6000 ticks.";
                case "read_region"->"Read every coordinate in inclusive min/max bounds (at most 1000000); prepare chunks while frozen, return immutable typed block artifact.";
                case "read_artifact"->"Retrieve immutable artifact entries at offset with limit 1..256; counts/hash and next_offset permit full reconstruction without silent truncation.";
                case "compare_traces"->"Compare exact trace state/events/clocks with explicit continuity validation; report first divergent tick and fields as an artifact, no normalization.";
                case "create_checkpoint"->"Create immutable flushed world checkpoint while frozen after established observed rest; incomplete door allowed, uncovered memory refused.";
                case "list_checkpoints"->"List all immutable checkpoint UUIDs and verified provenance/file hashes.";
                case "restore_checkpoint"->"Mutate attempt by requesting supervised restart to an immutable checkpoint; reconnect at same endpoint and inspect tick0 restoration comparison.";
                default->"TEST ONLY: controlled fixture/fault injection. Never enabled in campaign servers.";});
            switch(name) {
                case "start_attempt"->{properties.add("task_id",property("string"));JsonObject budget=integer(1,Integer.MAX_VALUE);JsonArray budgetTypes=new JsonArray();budgetTypes.add("integer");budgetTypes.add("null");budget.add("type",budgetTypes);properties.add("budget_tokens",budget);required.add("task_id");}
                case "advance", "act_input"->{properties.add("ticks",integer(1,6000));properties.add("trace",property("boolean"));required.add("ticks");}
                case "transition"->{properties.add("interact",property("boolean"));properties.add("max_ticks",integer(1,Rest.MAX_TICKS));properties.add("trace",property("boolean"));}
                case "check_geometry"->{JsonObject state=property("string");JsonArray choices=new JsonArray();choices.add("open");choices.add("closed");state.add("enum",choices);properties.add("expected_state",state);properties.add("frame_min_z",integer(-30000000,30000000));properties.add("frame_max_z",integer(-30000000,30000000));required.add("expected_state");}
                case "__test_geometry_entity"->{properties.add("present",property("boolean"));required.add("present");}
                case "__test_verification_mutate"->{for(String key:List.of("scenario","mode","boundary")){properties.add(key,property("string"));required.add(key);}properties.add("cycle",integer(1,5));required.add("cycle");}
                case "__test_transition_fixture", "__test_verification_fixture", "__test_verification_config"->{properties.add("scenario",property("string"));required.add("scenario");}
                case "read_region"->{JsonObject position=property("object"),coords=new JsonObject();JsonArray axes=new JsonArray();for(String axis:List.of("x","y","z")) {coords.add(axis,property("integer"));axes.add(axis);}position.add("properties",coords);position.add("required",axes);position.addProperty("additionalProperties",false);properties.add("min",position);properties.add("max",position.deepCopy());required.add("min");required.add("max");}
                case "read_artifact"->{properties.add("artifact_id",property("string"));properties.add("offset",integer(0,Integer.MAX_VALUE));properties.add("limit",integer(1,256));for(String key:List.of("artifact_id","offset","limit")) required.add(key);}
                case "compare_traces"->{properties.add("left",property("string"));properties.add("right",property("string"));required.add("left");required.add("right");}
                case "verify_checkpoint"->{properties.add("checkpoint_id",property("string"));required.add("checkpoint_id");properties.add("frame_min_z",integer(-30000000,30000000));properties.add("frame_max_z",integer(-30000000,30000000));}
                case "verification_status", "cancel_verification"->{properties.add("request_id",property("string"));required.add("request_id");}
                case "restore_checkpoint"->{properties.add("checkpoint_id",property("string"));required.add("checkpoint_id");}
                case "__test_checkpoint_compare"->{properties.add("checkpoint_id",property("string"));properties.add("count",integer(1,64));required.add("checkpoint_id");required.add("count");}
                case "read_blocks"->{JsonObject positions=property("array"),position=property("object"),coords=new JsonObject();for(String axis:List.of("x","y","z")) coords.add(axis,property("integer"));position.add("properties",coords);JsonArray axes=new JsonArray();axes.add("x");axes.add("y");axes.add("z");position.add("required",axes);positions.add("items",position);positions.addProperty("minItems",1);positions.addProperty("maxItems",256);properties.add("positions",positions);required.add("positions");}
                case "modify_blocks"->{JsonObject blocks=property("array");blocks.addProperty("minItems",1);blocks.addProperty("maxItems",256);blocks.add("items",placementSchema());properties.add("blocks",blocks);properties.add("notify_neighbors",property("boolean"));required.add("blocks");required.add("notify_neighbors");}
                case "prepare_input"->{properties.add("mode",property("string"));required.add("mode");}
                case "declare_input"->{properties.add("device",property("string"));properties.add("orientation",property("string"));JsonObject position=property("object"),coords=new JsonObject();JsonArray axes=new JsonArray();for(String axis:List.of("x","y","z")) {coords.add(axis,property("integer"));axes.add(axis);}position.add("properties",coords);position.add("required",axes);position.addProperty("additionalProperties",false);properties.add("position",position);properties.add("input_block",position.deepCopy());for(String key:List.of("device","orientation","position","input_block")) required.add(key);}
                case "__test_release_chunks"->properties.add("after_ticks",integer(0,6000));
            }
            schema.add("properties",properties);schema.add("required",required);schema.addProperty("additionalProperties",false);tool.add("inputSchema",schema);tools.add(tool);
        }
        return tools;
    }
    private static JsonObject error(JsonElement id,int code,String message) {JsonObject result=new JsonObject(),error=new JsonObject();result.addProperty("jsonrpc","2.0");result.add("id",id);error.addProperty("code",code);error.addProperty("message",message);result.add("error",error);return result;}
    private static void send(HttpExchange exchange,int status,JsonObject value) throws IOException {
        if(value==null) {exchange.sendResponseHeaders(status,-1);return;}
        byte[] body=JSON.toJson(value).getBytes(StandardCharsets.UTF_8);exchange.getResponseHeaders().set("Content-Type","application/json");exchange.sendResponseHeaders(status,body.length);exchange.getResponseBody().write(body);
    }
    @Override public void close() {http.stop(1);executor.shutdownNow();}
}
