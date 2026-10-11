package stonebench;

import com.google.gson.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.block.Blocks;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.server.world.ChunkLevelType;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.math.ChunkPos;
import net.minecraft.world.rule.GameRules;
import stonebench.mixin.TickManagerAccess;

/** One controller per dedicated server. Every world access occurs inside server tick hooks. */
public final class Controller implements ModInitializer {
    private static final Gson JSON = new GsonBuilder().serializeNulls().disableHtmlEscaping().create();
    private static final ConcurrentLinkedQueue<Operation> QUEUE = new ConcurrentLinkedQueue<>();
    private static final Set<Long> CHUNKS = new LinkedHashSet<>();
    private static MinecraftServer server;
    private static McpHttp transport;
    private static Operation active;
    private static JsonObject task;
    private static String attempt;
    private static long simulationTicks, preparationTicks;
    private static int releaseAt;
    public static final boolean TEST = Boolean.getBoolean("stonebench.test");

    private static final class Operation {
        final String id=UUID.randomUUID().toString(), tool;
        final JsonObject args;
        final CompletableFuture<JsonObject> result=new CompletableFuture<>();
        long deadline;
        String phase="validation";
        long beforeTime;
        int executed, requested;
        boolean mutated, preparationInitialLoaded, preparationInitialReady;
        Runnable continuation; List<Construction.Placement> placements;
        boolean trace;
        JsonObject initial;
        long startWorldTime,startTimeOfDay,startSimulationIndex;
        final List<JsonObject> observations=new ArrayList<>();
        Operation(String tool,JsonObject args) {this.tool=tool;this.args=args;}
    }
    @Override public void onInitialize() {}
    public static void boot(MinecraftServer value) {
        server=value;
        world().getGameRules().setValue(GameRules.RANDOM_TICK_SPEED,0,server);
        world().getGameRules().setValue(GameRules.DO_MOB_SPAWNING,false,server);
        world().getGameRules().setValue(GameRules.ADVANCE_WEATHER,false,server);
        try {
            transport=new McpHttp(Integer.getInteger("stonebench.port",18765));
            Files.createDirectories(Path.of("stonebench"));
            Files.writeString(Path.of("stonebench/ready"), "Minecraft 1.21.11; MCP listening\n");
        } catch (IOException e) { throw new UncheckedIOException(e); }
    }
    public static CompletableFuture<JsonObject> submit(String tool,JsonObject args) {
        Operation operation=new Operation(tool,args); QUEUE.add(operation); return operation.result;
    }
    public static void beforeTick() {
        if (server==null) return;
        // Prevent ordinary console tick commands from changing the benchmark clock.
        if (active==null) freeze();
        if (active!=null && active.phase.equals("simulation") && !ready()) {
            fail("infrastructure","chunks_unavailable","Relevant chunks lost block/entity ticking readiness");
        }
        if (active!=null && System.nanoTime()>active.deadline) fail("infrastructure","operation_timeout","Wall-clock safety deadline reached");
        if (active==null) {
            active=QUEUE.poll();
            if (active!=null) {
                try { Observation.start();active.deadline=System.nanoTime()+420_000_000_000L; dispatch(); }
                catch (UnsupportedOperationException e) { fail("unsupported","unsupported_component",e.getMessage()); }
                catch (IllegalArgumentException e) { fail("validation","invalid_arguments",e.getMessage()); }
                catch (Exception e) { fail("infrastructure","server_error",e.toString()); }
            }
        }
        if (active!=null) active.beforeTime=world().getTime();
    }
    public static void afterTick() {
        if (active==null) return;
        try {
            long delta=world().getTime()-active.beforeTime;
            if (delta<0 || delta>1) throw new IllegalStateException("Unexpected world-time delta: "+delta);
            if (active.phase.equals("preparation")) {
                preparationTicks+=delta;
                if (ready()) {
                    if (active.tool.equals("start_attempt")) {
                        // The whole generator is air. Preparation cannot tick a prior construction.
                        for (BlockPos pos:BlockPos.iterate(1024,64,1024,1039,111,1039))
                            if (!world().getBlockState(pos).isAir()) throw new IllegalStateException("Initial region is not empty");
                        JsonObject metadata=description();
                        Files.writeString(Path.of("stonebench/attempt.json"),JSON.toJson(metadata),StandardOpenOption.CREATE_NEW);
                    }
                    if(active.continuation!=null) {freeze();active.phase="mutation";active.continuation.run();} else succeed(description());
                } else if(active.continuation==null) step();
            } else if (active.phase.equals("simulation")) {
                active.executed+=delta; simulationTicks+=delta;
                if(delta==1 && active.trace) active.observations.add(Observation.sample(world(),active.executed,simulationTicks,"end_tick",Observation.raw(world())));
                if (releaseAt>0 && active.executed>=releaseAt) { force(false); releaseAt=0; }
                if (!ready()) fail("infrastructure","chunks_unavailable","Relevant chunks lost block/entity ticking readiness");
                else if (active.executed==active.requested) succeed(observedResult());
                else {Observation.begin(simulationTicks+1,active.executed+1,"before_world_time");step();}
            }
        } catch (Exception e) { fail("infrastructure","server_error",e.toString()); }
    }
    private static void dispatch() {
        Set<String> allowed=switch(active.tool) {
            case "start_attempt" -> Set.of("task_id","budget_tokens");
            case "advance" -> Set.of("ticks","trace");
            case "read_blocks" -> Set.of("positions");
            case "read_region" -> Set.of("min","max");
            case "read_artifact" -> Set.of("artifact_id","offset","limit");
            case "compare_traces" -> Set.of("left","right");
            case "modify_blocks" -> Set.of("blocks","notify_neighbors");
            case "__test_release_chunks" -> Set.of("after_ticks");
            default -> Set.of();
        };
        if(!allowed.containsAll(active.args.keySet())) throw new IllegalArgumentException("Unexpected argument");
        if (!server.isOnThread()) throw new IllegalStateException("Operation outside server thread");
        if (!active.tool.equals("start_attempt") && task==null) throw new IllegalArgumentException("start_attempt is required");
        switch(active.tool) {
            case "start_attempt" -> {
                if (task!=null || Files.exists(Path.of("stonebench/attempt.json"))) throw new IllegalArgumentException("already_started: each attempt needs a fresh server directory");
                JsonObject selected=Task.describe(Task.string(active.args,"task_id"),active.args.has("budget_tokens") && !active.args.get("budget_tokens").isJsonNull() ? Task.integer(active.args,"budget_tokens",1,Integer.MAX_VALUE) : null);
                task=selected; attempt=UUID.randomUUID().toString(); active.mutated=true;
                CHUNKS.add(ChunkPos.toLong(64,64)); force(true);
                active.preparationInitialLoaded=world().getChunkManager().getWorldChunk(64,64)!=null; active.preparationInitialReady=ready();
                active.phase="preparation"; step();
            }
            case "describe_task" -> succeed(description());
            case "describe_blocks" -> succeed(BlockCatalog.describe());
            case "modify_blocks" -> {
                active.placements=Construction.validate(world(),active.args);
                for(var p:active.placements) {Observation.track(p.pos());for(var direction:net.minecraft.util.math.Direction.values()) Observation.track(p.pos().offset(direction));}
                Set<ChunkPos> chunks=new LinkedHashSet<>();
                for(var p:active.placements) for(int dx=-1;dx<=1;dx++) for(int dz=-1;dz<=1;dz++) chunks.add(new ChunkPos(p.pos().add(dx,0,dz)));
                Runnable placement=()->{active.phase="mutation";active.initial=Observation.raw(world());active.startWorldTime=world().getTime();active.startTimeOfDay=world().getTimeOfDay();active.startSimulationIndex=simulationTicks;Observation.begin(simulationTicks,0,"mutation_between_ticks");active.mutated=true;JsonObject result=Construction.apply(world(),active.placements,active.args.get("notify_neighbors").getAsBoolean());for(var e:observedResult().entrySet()) result.add(e.getKey(),e.getValue());succeed(result);};
                if(chunks.stream().allMatch(c->CHUNKS.contains(c.toLong())) && ready()) placement.run();
                else prepareChunks(chunks,placement);
            }
            case "read_blocks" -> {
                JsonElement value=active.args.get("positions");
                if (value==null || !value.isJsonArray() || value.getAsJsonArray().size()<1 || value.getAsJsonArray().size()>256)
                    throw new IllegalArgumentException("positions must contain 1..256 positions; split larger reads explicitly");
                List<BlockPos> positions=new ArrayList<>();
                for(JsonElement item:value.getAsJsonArray()) {
                    if(!item.isJsonObject()) throw new IllegalArgumentException("position must be an object");
                    JsonObject p=item.getAsJsonObject();
                    BlockPos pos=new BlockPos(Task.integer(p,"x",-30000000,30000000),Task.integer(p,"y",world().getBottomY(),world().getTopYInclusive()),Task.integer(p,"z",-30000000,30000000));
                    if (!CHUNKS.contains(new ChunkPos(pos).toLong())) throw new IllegalArgumentException("scope_unprepared: coordinate outside prepared chunks");
                    positions.add(pos);
                }
                if (!ready()) { fail("infrastructure","chunks_unavailable","Read requires ticking-ready chunks"); return; }
                JsonArray blocks=new JsonArray();
                for(BlockPos pos:positions) {
                    Observation.track(pos);
                    blocks.add(BlockCatalog.read(world(),pos));
                }
                JsonObject result=new JsonObject();result.add("blocks",blocks);succeed(result);
            }
            case "advance" -> {
                active.requested=Task.integer(active.args,"ticks",1,6000);
                if(active.args.has("trace") && (!active.args.get("trace").isJsonPrimitive() || !active.args.get("trace").getAsJsonPrimitive().isBoolean())) throw new IllegalArgumentException("trace must be a boolean");
                active.trace=active.args.has("trace") && active.args.get("trace").getAsBoolean();
                if (!ready()) {fail("infrastructure","chunks_unavailable","Simulation requires block and block-entity ticking readiness");return;}
                if(server.getPlayerManager().getCurrentPlayerCount()!=0) {fail("infrastructure","players_present","Dedicated attempts cannot contain players");return;}
                active.initial=Observation.raw(world());active.startWorldTime=world().getTime();active.startTimeOfDay=world().getTimeOfDay();active.startSimulationIndex=simulationTicks;
                active.phase="simulation";Observation.begin(simulationTicks+1,1,"before_world_time");active.mutated=true;step();
            }
            case "read_region" -> {
                List<BlockPos> positions=Observation.region(active.args,world());Set<ChunkPos> chunks=new LinkedHashSet<>();for(var p:positions) chunks.add(new ChunkPos(p));
                Runnable read=()->{active.phase="observation";succeed(Observation.readRegion(world(),positions));};
                if(chunks.stream().allMatch(c->CHUNKS.contains(c.toLong())) && ready()) read.run();else prepareChunks(chunks,read);
            }
            case "read_artifact" -> succeed(Artifacts.read(active.args));
            case "compare_traces" -> succeed(Observation.compareTraces(active.args));
            case "__test_outside_influence" -> {
                requireTest();BlockPos outside=new BlockPos(1120,80,1120);world().getChunk(new ChunkPos(outside).x,new ChunkPos(outside).z);
                active.initial=Observation.raw(world());active.startWorldTime=world().getTime();active.startTimeOfDay=world().getTimeOfDay();active.startSimulationIndex=simulationTicks;
                Observation.begin(simulationTicks,0,"test_fault_between_ticks");active.mutated=true;
                world().scheduleBlockTick(outside,Blocks.STONE,5);succeed(observedResult());
            }
            case "__test_default_wire" -> {requireTest();active.mutated=true;world().setBlockState(new BlockPos(1036,80,1030),Blocks.REDSTONE_WIRE.getDefaultState(),net.minecraft.block.Block.FORCE_STATE_AND_SKIP_CALLBACKS_AND_DROPS);JsonObject result=new JsonObject();result.add("block",BlockCatalog.read(world(),new BlockPos(1036,80,1030)));succeed(result);}
            case "__test_fail_next_lot" -> {requireTest();Construction.failNextLot=true;succeed(new JsonObject());}
            case "__test_release_chunks" -> {
                requireTest();releaseAt=active.args.has("after_ticks")?Task.integer(active.args,"after_ticks",0,6000):0;
                if(releaseAt==0) force(false);active.mutated=true;succeed(new JsonObject());
            }
            case "__test_restore_chunks" -> {requireTest();force(true);active.mutated=true;active.phase="preparation";step();}
            case "__test_place_block" -> {
                requireTest();if(!ready()) throw new IllegalStateException("Chunks unavailable");
                world().setBlockState(new BlockPos(1024,80,1024),Blocks.STONE.getDefaultState(),3);
                active.mutated=true;succeed(new JsonObject());
            }
            default -> throw new IllegalArgumentException("Unknown tool: "+active.tool);
        }
    }
    private static void requireTest() {if(!TEST) throw new IllegalArgumentException("Unknown tool");}
    public static ServerWorld world() {return server==null?null:server.getOverworld();}
    public static boolean prepared(BlockPos pos) {return CHUNKS.contains(new ChunkPos(pos).toLong());}
    public static boolean observationReady() {return ready();}
    public static void observationPhase(String value) {Observation.phase(value);}
    public static void observeBaseline(BlockPos pos) {
        if(active!=null && active.initial!=null && prepared(pos)) {
            var blocks=active.initial.getAsJsonObject("blocks");String key=pos.getX()+","+pos.getY()+","+pos.getZ();
            if(!blocks.has(key)) blocks.add(key,BlockCatalog.read(world(),pos));
        }
    }
    private static JsonObject observedResult() {
        JsonObject result=new JsonObject();if(active.initial==null) return result;
        JsonObject end=Observation.raw(world());JsonArray differences=ObservationComparison.fields(active.initial,end);List<JsonElement> rows=new ArrayList<>();differences.forEach(rows::add);result.add("diff",Artifacts.write("initial_final_diff",rows));result.add("coverage",Observation.coverage());
        if(active.trace) {
            JsonObject metadata=new JsonObject();metadata.addProperty("expected_ticks",active.requested);metadata.addProperty("start_world_time",active.startWorldTime);metadata.addProperty("start_simulation_index",active.startSimulationIndex);
            result.add("trace",Artifacts.write("trace",active.observations,metadata));result.add("continuity",ObservationComparison.continuity(active.observations,active.requested,active.startWorldTime,active.startSimulationIndex));
        }
        result.add("initial",Observation.sample(world(),0,active.startSimulationIndex,"initial",active.initial));
        result.getAsJsonObject("initial").addProperty("world_time",active.startWorldTime);
        result.getAsJsonObject("initial").addProperty("time_of_day",active.startTimeOfDay);
        result.getAsJsonObject("initial").add("events",Artifacts.write("intratick_events",List.of()));
        result.add("final",Observation.sample(world(),active.executed,simulationTicks,"final",end));
        result.add("intratick_events",Artifacts.write("intratick_events",Observation.operationEvents()));return result;
    }
    private static void force(boolean value) {
        for(long key:CHUNKS) {ChunkPos c=new ChunkPos(key);world().setChunkForced(c.x,c.z,value);if(value) world().getChunk(c.x,c.z);}
    }
    private static boolean ready() {
        if(CHUNKS.isEmpty()) return false;
        for(long key:CHUNKS) {
            ChunkPos c=new ChunkPos(key);
            if (!world().shouldTickBlocksInChunk(key) || !world().isTickingFutureReady(key)
                || world().getChunkManager().getWorldChunk(c.x,c.z)==null
                || !world().getChunk(c.x,c.z).getLevelType().isAfter(ChunkLevelType.BLOCK_TICKING)) return false;
        }
        return true;
    }
        private static void freeze() {
        server.getTickManager().stopStepping();server.getTickManager().setFrozen(true);
        ((TickManagerAccess)server.getTickManager()).stonebench$shouldTick(false);
    }
    /** Extension seam for placement/observation: call on server thread before any mutation. */
    public static void prepareChunks(Collection<ChunkPos> chunks) {prepareChunks(chunks,null);}
    /** Resume an operation after frozen chunk preparation; completion belongs to its action. */
    public static void prepareChunks(Collection<ChunkPos> chunks,Runnable continuation) {
        if (!server.isOnThread() || active==null) throw new IllegalStateException("Preparation requires an active server-thread operation");
        active.continuation=continuation;
        for(ChunkPos chunk:chunks) CHUNKS.add(chunk.toLong());
        force(true); active.phase="preparation"; if(active.continuation==null) step(); else freeze();
    }
    private static void step() {if(!server.getTickManager().step(1)) throw new IllegalStateException("Vanilla tick manager refused step");}
    private static JsonObject description() {
        JsonObject result=new JsonObject();result.addProperty("attempt_id",attempt);result.add("task",task==null?JsonNull.INSTANCE:task.deepCopy());result.addProperty("chunks_ready",ready());
        result.addProperty("preparation_ticks",preparationTicks);
        JsonObject environment=new JsonObject();environment.addProperty("minecraft","1.21.11");environment.addProperty("yarn","1.21.11+build.3");
        environment.addProperty("fabric_loader",FabricLoader.getInstance().getModContainer("fabricloader").orElseThrow().getMetadata().getVersion().getFriendlyString());
        environment.addProperty("controller","0.1.0");environment.addProperty("java",System.getProperty("java.version"));environment.addProperty("tick_rate",server.getTickManager().getTickRate());
        environment.addProperty("seed",world().getSeed());environment.addProperty("generator","flat_air");environment.addProperty("random_tick_speed",world().getGameRules().getValue(GameRules.RANDOM_TICK_SPEED));
        environment.addProperty("mob_spawning",world().getGameRules().getValue(GameRules.DO_MOB_SPAWNING));
        environment.addProperty("advance_weather",world().getGameRules().getValue(GameRules.ADVANCE_WEATHER));
        environment.addProperty("players_allowed",false);environment.addProperty("server_directory",Path.of("").toAbsolutePath().toString());
        result.add("environment",environment);return result;
    }
    private static JsonObject envelope(String status) {
        JsonObject result=new JsonObject();result.addProperty("operation_id",active.id);result.addProperty("operation",active.tool);result.addProperty("attempt_id",attempt);
        result.addProperty("phase",active.phase);result.addProperty("status",status);result.addProperty("ticks_executed",active.executed);
        result.addProperty("simulation_ticks",simulationTicks);result.addProperty("preparation_ticks",preparationTicks);result.addProperty("world_time",world().getTime());
        result.addProperty("preparation_initial_loaded",active.preparationInitialLoaded);result.addProperty("preparation_initial_ready",active.preparationInitialReady);
        result.addProperty("frozen",server.getTickManager().isFrozen());result.addProperty("mutated",active.mutated);return result;
    }
    private static void finish(JsonObject result) {
        freeze();
        Observation.end();
        try { Files.writeString(Path.of("stonebench/operations.jsonl"),JSON.toJson(result)+"\n",StandardOpenOption.CREATE,StandardOpenOption.APPEND); }
        catch(IOException e) {
            result.addProperty("status","error");JsonObject error=new JsonObject();error.addProperty("kind","infrastructure");error.addProperty("code","journal_write_failed");error.addProperty("message",e.toString());result.add("error",error);
        }
        active.result.complete(result);active=null;
    }
    private static void succeed(JsonObject payload) {
        freeze();
        JsonObject result=envelope("ok");for(var entry:payload.entrySet()) result.add(entry.getKey(),entry.getValue());finish(result);
    }
    private static void fail(String kind,String code,String message) {
        if(active==null) return;
        freeze();
        JsonObject result=envelope("error"),error=new JsonObject();error.addProperty("kind",kind);error.addProperty("code",code);error.addProperty("message",message);
        error.addProperty("effects",active.mutated?"World may have changed; inspect reported effective state before retry":"No mutation performed");result.add("error",error);
        try {for(var e:observedResult().entrySet()) result.add(e.getKey(),e.getValue());} catch(Exception observationError) {result.addProperty("observation_incomplete",true);result.addProperty("observation_error",observationError.toString());}
        if(active.placements!=null && active.mutated) {result.add("blocks",Construction.read(world(),active.placements));result.addProperty("recovery","Inspect actual blocks; retry a validated repair lot or restore a checkpoint when checkpoint support is available");}finish(result);
    }
    public static void shutdown() {
        if(active!=null) fail("infrastructure","server_stopped","Server shutdown interrupted operation");
        Operation operation;while((operation=QUEUE.poll())!=null) {active=operation;fail("infrastructure","server_stopped","Server stopped before operation");}
        if(transport!=null) transport.close();
    }
}
