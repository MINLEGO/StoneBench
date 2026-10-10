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
                    result=new JsonObject();result.add("structuredContent",report);result.addProperty("isError",report.get("status").getAsString().equals("error"));
                    JsonObject content=new JsonObject();content.addProperty("type","text");content.addProperty("text",JSON.toJson(report));JsonArray contents=new JsonArray();contents.add(content);result.add("content",contents);
                }
                default -> {send(exchange,200,error(id,-32601,"Method not found"));return;}
            }
            JsonObject response=new JsonObject();response.addProperty("jsonrpc","2.0");response.add("id",id);response.add("result",result);send(exchange,200,response);
        } catch(InterruptedException e) {Thread.currentThread().interrupt();send(exchange,503,null);}
        catch(ExecutionException e) {send(exchange,503,null);}
        catch(RuntimeException e) {send(exchange,400,error(JsonNull.INSTANCE,-32600,"Invalid request"));}
        finally {exchange.close();}
    }
    private static Set<String> names() {
        Set<String> names=new LinkedHashSet<>(List.of("start_attempt","describe_task","read_blocks","advance"));
        if(Controller.TEST) names.addAll(List.of("__test_release_chunks","__test_restore_chunks","__test_place_block"));return names;
    }
    private static JsonObject property(String type) {JsonObject p=new JsonObject();p.addProperty("type",type);return p;}
    private static JsonObject integer(int min,int max) {JsonObject p=property("integer");p.addProperty("minimum",min);p.addProperty("maximum",max);return p;}
    private static JsonArray tools() {
        JsonArray tools=new JsonArray();
        for(String name:names()) {
            JsonObject tool=new JsonObject(),schema=property("object"),properties=new JsonObject();JsonArray required=new JsonArray();
            tool.addProperty("name",name);tool.addProperty("description",switch(name) {
                case "start_attempt"->"Initialize one fresh isolated regular DOOR attempt; budget in tokens is supplied by the caller.";
                case "describe_task"->"Describe immutable task, effective clock, environment and chunk readiness.";
                case "read_blocks"->"Read 1..256 actual block states in prepared chunks; larger reads must be split.";
                case "advance"->"Advance exactly 1..6000 vanilla world ticks and return frozen; infrastructure failure reports partial effects.";
                default->"TEST ONLY: controlled fixture/fault injection. Never enabled in campaign servers.";});
            switch(name) {
                case "start_attempt"->{properties.add("task_id",property("string"));JsonObject budget=integer(1,Integer.MAX_VALUE);JsonArray budgetTypes=new JsonArray();budgetTypes.add("integer");budgetTypes.add("null");budget.add("type",budgetTypes);properties.add("budget_tokens",budget);required.add("task_id");}
                case "advance"->{properties.add("ticks",integer(1,6000));required.add("ticks");}
                case "read_blocks"->{JsonObject positions=property("array"),position=property("object"),coords=new JsonObject();for(String axis:List.of("x","y","z")) coords.add(axis,property("integer"));position.add("properties",coords);JsonArray axes=new JsonArray();axes.add("x");axes.add("y");axes.add("z");position.add("required",axes);positions.add("items",position);positions.addProperty("minItems",1);positions.addProperty("maxItems",256);properties.add("positions",positions);required.add("positions");}
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
