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
    private static boolean artifactRecovery;
    private static boolean resumeLoading,restorePending,restoreFailed;
    private static JsonObject resume,restoration;
    private static JsonObject resumePreparationBefore;
    private static long resumeInitialWorldTime;
    private static int releaseAt;
    // Native sprint is the default after real fixture equivalence; unit stepping stays an explicit reference.
    private static final String TICK_EXECUTION=System.getProperty("stonebench.tickExecution","sprint");
    private static final int TEST_INITIAL_PREPARATION_TICKS=Boolean.getBoolean("stonebench.test")?Integer.getInteger("stonebench.initialPreparationTicks",0):0;
    public static final boolean TEST = Boolean.getBoolean("stonebench.test");

    private static final class Operation {
        final String id=UUID.randomUUID().toString(), tool;
        final JsonObject args;
        final CompletableFuture<JsonObject> result=new CompletableFuture<>();
        long deadline, simulationStartedNanos;
        String phase="validation";
        long beforeTime;
        int executed, requested;
        boolean mutated, preparationInitialLoaded, preparationInitialReady;
        Runnable continuation; List<Construction.Placement> placements;
        boolean trace; Transition transition;
        JsonObject initial;
        long startWorldTime,startTimeOfDay,startSimulationIndex;
        final List<JsonObject> observations=new ArrayList<>();
        Operation(String tool,JsonObject args) {this.tool=tool;this.args=args;}
    }
    @Override public void onInitialize() {}
    public static void boot(MinecraftServer value) {
        server=value;
        if(!Set.of("unit","sprint").contains(TICK_EXECUTION)) throw new IllegalArgumentException("tickExecution must be unit or sprint");
        world().getGameRules().setValue(GameRules.RANDOM_TICK_SPEED,0,server);
        world().getGameRules().setValue(GameRules.DO_MOB_SPAWNING,false,server);
        world().getGameRules().setValue(GameRules.ADVANCE_WEATHER,false,server);
        try {
            Files.createDirectories(Path.of("stonebench"));
            recoverArtifactIdentity();
            freeze();
            Path marker=Path.of("stonebench/resume.json");
            if(Files.exists(marker)) {
                resume=CheckpointStorage.read(marker);
                JsonObject context=Checkpoints.context(Task.string(resume,"checkpoint_id"));
                if(!attempt.equals(Task.string(context,"attempt_id")) || !attempt.equals(Task.string(resume,"attempt_id"))) throw new IOException("Restored attempt identity mismatch");
                if(context.get("format").getAsInt()!=1) throw new IOException("Unsupported checkpoint context format");
                simulationTicks=context.get("simulation_ticks").getAsLong();preparationTicks=context.get("preparation_ticks").getAsLong();
                task=context.getAsJsonObject("task").deepCopy();
                for(JsonElement item:context.getAsJsonArray("chunks")) {JsonObject chunk=item.getAsJsonObject();CHUNKS.add(ChunkPos.toLong(Task.integer(chunk,"x",-1875000,1875000),Task.integer(chunk,"z",-1875000,1875000)));}
                Observation.restoreContext(context.getAsJsonObject("observation"),world());
                resumeLoading=true;force(true);
                resumeInitialWorldTime=world().getTime();resumePreparationBefore=checkpointSnapshot();
            } else openTransport();
        } catch (IOException e) { throw new UncheckedIOException(e); }
    }
    private static void openTransport() throws IOException {
        transport=new McpHttp(Integer.getInteger("stonebench.port",18765));
        Files.writeString(Path.of("stonebench/ready"),"Minecraft 1.21.11; MCP listening\n");
    }
    private static void finishResume() throws IOException {
        JsonObject context=Checkpoints.context(Task.string(resume,"checkpoint_id"));
        Inputs.restoreContext(context.getAsJsonObject("input"),world());
        JsonObject actual=checkpointSnapshot();
        JsonObject comparison=Checkpoints.compareRestored(Task.string(resume,"checkpoint_id"),actual);
        restoration=resume.deepCopy();restoration.add("comparison",comparison);restoration.addProperty("chunks_ready",ready());
        long preparationGameTicks=world().getTime()-resumeInitialWorldTime;
        JsonArray preparationChanges=ObservationComparison.fields(resumePreparationBefore,actual);boolean preserved=true;
        for(JsonElement item:preparationChanges) if(!item.getAsJsonObject().get("field").getAsString().startsWith("$.state.coverage.")) preserved=false;
        restoration.add("preparation_changes",Artifacts.write("checkpoint_preparation_diff",preparationChanges.asList()));
        restoration.addProperty("preparation_initial_chunks_ready",resumePreparationBefore.getAsJsonObject("state").getAsJsonObject("coverage").get("chunks_ready").getAsBoolean());
        restoration.addProperty("preparation_construction_preserved",preserved);restoration.addProperty("preparation_game_ticks",preparationGameTicks);restoration.addProperty("status",comparison.get("status").getAsString());
        if(preparationGameTicks!=0 || !preserved) {comparison.addProperty("status","different");restoration.addProperty("status","different");Checkpoints.invalidateRest();}
        restoreFailed=!comparison.get("status").getAsString().equals("equal");artifactRecovery=false;resumeLoading=false;
        Files.writeString(Path.of("stonebench/restoration.json"),JSON.toJson(restoration));
        // An explicit journal segment preserves prior clock history instead of rewriting it.
        JsonObject row=new JsonObject();row.addProperty("operation_id",UUID.randomUUID().toString());row.addProperty("operation","restore_boot");row.addProperty("attempt_id",attempt);
        row.addProperty("phase","before_first_useful_tick");row.addProperty("status",restoreFailed?"error":"ok");row.addProperty("ticks_executed",0);
        row.addProperty("simulation_ticks",simulationTicks);row.addProperty("preparation_ticks",preparationTicks);row.addProperty("world_time",world().getTime());row.addProperty("frozen",true);row.addProperty("mutated",true);row.add("restoration",restoration.deepCopy());
        if(restoreFailed) {JsonObject error=new JsonObject();error.addProperty("kind","infrastructure");error.addProperty("code","checkpoint_divergence");row.add("error",error);}
        Files.writeString(Path.of("stonebench/operations.jsonl"),JSON.toJson(row)+"\n",StandardOpenOption.CREATE,StandardOpenOption.APPEND);
        Files.move(Path.of("stonebench/resume.json"),Path.of("stonebench/restore-history",Task.string(resume,"request_id"),"resume-completed.json"));
        openTransport();
    }
    /** Recover immutable evidence and reporting counters only; no task/chunks/simulation resume. */
    private static void recoverArtifactIdentity() throws IOException {
        Path metadata=Path.of("stonebench/attempt.json");
        if(!Files.exists(metadata)) return;
        JsonObject saved=JsonParser.parseString(Files.readString(metadata)).getAsJsonObject();
        attempt=UUID.fromString(saved.get("attempt_id").getAsString()).toString();
        Path journal=Path.of("stonebench/operations.jsonl");
        JsonObject last=null;
        if(Files.exists(journal)) try(var reader=Files.newBufferedReader(journal)) {
            String line;while((line=reader.readLine())!=null) {
                JsonObject entry=JsonParser.parseString(line).getAsJsonObject();
                if(entry.get("attempt_id").isJsonNull() && last==null) continue; // Validation failures before the attempt was created.
                if(!attempt.equals(entry.get("attempt_id").getAsString())) throw new IOException("Journal attempt identity mismatch");
                last=entry;
            }
        }
        if(last!=null) {
            simulationTicks=new java.math.BigDecimal(last.get("simulation_ticks").getAsString()).longValueExact();
            preparationTicks=new java.math.BigDecimal(last.get("preparation_ticks").getAsString()).longValueExact();
            if(simulationTicks<0 || preparationTicks<0) throw new IOException("Invalid historical counters");
        }
        artifactRecovery=true;
    }
    public static CompletableFuture<JsonObject> submit(String tool,JsonObject args) {
        Operation operation=new Operation(tool,args); QUEUE.add(operation); return operation.result;
    }
    public static void beforeTick() {
        if (server==null) return;
        if(resumeLoading) {
            freeze();
            try {if(ready()) finishResume();} catch(Exception e) {throw new IllegalStateException("Checkpoint boot comparison failed",e);}
            return;
        }
        // Prevent ordinary console tick commands from changing the benchmark clock.
        if (active==null) freeze();
        if(Verification.running()){freeze();try {Verification.poll(Controller::checkpointSnapshot);}catch(IOException e){throw new IllegalStateException("Verification result archive failed",e);}}
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
                if (ready() && (!active.tool.equals("start_attempt") || preparationTicks>=TEST_INITIAL_PREPARATION_TICKS)) {
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
                JsonObject raw=delta==1 && (active.trace || active.transition!=null)?Observation.raw(world()):null;
                JsonObject sample=delta==1 && active.trace?Observation.sample(world(),active.executed,simulationTicks,"end_tick",raw):null;
                if(sample!=null) active.observations.add(sample);
                if (releaseAt>0 && active.executed>=releaseAt) { force(false); releaseAt=0; }
                if (!ready()) fail("infrastructure","chunks_unavailable","Relevant chunks lost block/entity ticking readiness");
                else if(delta==1 && active.transition!=null && active.transition.tick(raw,Observation.currentEvents(),active.executed)) {
                    if(sample!=null) sample.add("rest",active.transition.report());
                    active.requested=active.executed;JsonObject result=observedResult();result.add("transition",active.transition.report());
                    Checkpoints.recordRest(checkpointSnapshot(),active.transition.report());succeed(result);
                }
                else if (active.executed==active.requested) succeed(observedResult());
                else {if(sample!=null && active.transition!=null) sample.add("rest",active.transition.report());if(delta==1) Observation.begin(simulationTicks+1,active.executed+1,"before_world_time");if(TICK_EXECUTION.equals("unit")) step();}
            }
        } catch (UnsupportedOperationException e) {fail("unsupported","unsupported_component",e.getMessage());}
        catch (IllegalArgumentException e) {fail("validation","invalid_arguments",e.getMessage());}
        catch (Exception e) { fail("infrastructure","server_error",e.toString()); }
    }
    private static void dispatch() throws IOException {
        Set<String> allowed=switch(active.tool) {
            case "start_attempt" -> Set.of("task_id","budget_tokens");
            case "advance", "act_input" -> Set.of("ticks","trace");
            case "transition" -> Set.of("max_ticks","trace","interact");
            case "verify_checkpoint" -> Set.of("checkpoint_id","frame_min_z","frame_max_z");
            case "verification_status", "cancel_verification" -> Set.of("request_id");
            case "check_geometry" -> Set.of("expected_state","frame_min_z","frame_max_z");
            case "__test_geometry_entity" -> Set.of("present");
            case "__test_transition_fixture", "__test_verification_fixture", "__test_verification_config" -> Set.of("scenario");
            case "__test_verification_mutate" -> Set.of("scenario","cycle","mode","boundary");
            case "declare_input" -> Set.of("device","position","orientation","input_block");
            case "prepare_input" -> Set.of("mode");
            case "read_blocks" -> Set.of("positions");
            case "read_region" -> Set.of("min","max");
            case "read_artifact" -> Set.of("artifact_id","offset","limit");
            case "compare_traces" -> Set.of("left","right");
            case "restore_checkpoint" -> Set.of("checkpoint_id");
            case "__test_checkpoint_compare" -> Set.of("checkpoint_id","count");
            case "modify_blocks" -> Set.of("blocks","notify_neighbors");
            case "__test_release_chunks" -> Set.of("after_ticks");
            default -> Set.of();
        };
        if(!allowed.containsAll(active.args.keySet())) throw new IllegalArgumentException("Unexpected argument");
        if (!server.isOnThread()) throw new IllegalStateException("Operation outside server thread");
        if(Verification.running() && !Set.of("verification_status","cancel_verification","verification_snapshot","describe_task","describe_rules","describe_blocks","list_checkpoints","read_artifact","compare_traces").contains(active.tool))throw new IllegalArgumentException("Verification owns frozen working state; cancel or await its completion before mutation, simulation or expanding observation coverage");
        if((restorePending || restoreFailed) && !Set.of("describe_task","list_checkpoints","restore_checkpoint","read_artifact","compare_traces").contains(active.tool)) throw new IllegalArgumentException("Restore pending or divergent: reconnect/inspect restoration or restore a valid checkpoint before simulation");
        boolean evidenceRead=Set.of("read_artifact","compare_traces","list_checkpoints","restore_checkpoint","describe_task","verification_status").contains(active.tool);
        if (!active.tool.equals("start_attempt") && task==null && !(artifactRecovery && evidenceRead)) throw new IllegalArgumentException("start_attempt is required; recovered attempts permit immutable evidence reads only");
        if(artifactRecovery) active.phase="artifact_recovery";
        switch(active.tool) {
            case "verify_checkpoint" -> {
                if(!Boolean.getBoolean("stonebench.verificationSupervisor")) throw new IllegalArgumentException("verify_checkpoint requires the owning verification supervisor");
                JsonObject frame=active.args.deepCopy();frame.remove("checkpoint_id");frame.addProperty("expected_state","closed");RegularDoorGeometry.frame(task,frame);
                succeed(Verification.start(active.args,attempt,checkpointSnapshot()));
            }
            case "verification_status" -> succeed(Verification.status(active.args));
            case "cancel_verification" -> succeed(Verification.cancel(active.args));
            case "verification_snapshot" -> {JsonObject result=new JsonObject();result.add("checkpoint_state",checkpointSnapshot());result.add("construction",Inputs.construction(Observation.raw(world())));result.add("input",Inputs.declared());succeed(result);}
            case "create_checkpoint" -> {
                if(server.getPlayerManager().getCurrentPlayerCount()!=0) throw new IllegalArgumentException("Checkpoint requires no players");
                if(!ready()) throw new IllegalStateException("Chunks unavailable");
                active.phase="checkpoint_between_ticks";
                JsonObject result=Checkpoints.create(server.getSavePath(net.minecraft.util.WorldSavePath.ROOT),checkpointSnapshot(),checkpointContext(),description().getAsJsonObject("environment"),server.getTickManager().isFrozen() && !server.getTickManager().isSprinting() && !server.getTickManager().isStepping(),()->server.save(false,true,true));
                succeed(result);
            }
            case "list_checkpoints" -> succeed(Checkpoints.list());
            case "restore_checkpoint" -> {
                if(!Boolean.getBoolean("stonebench.supervised")) throw new IllegalArgumentException("restore_checkpoint requires the owning restart supervisor");
                String id=Task.string(active.args,"checkpoint_id");JsonObject request;
                if(restorePending) {
                    request=CheckpointStorage.read(Path.of("stonebench/restore-request.json"));
                    if(!id.equals(Task.string(request,"checkpoint_id"))) throw new IllegalArgumentException("Different restore already pending");
                } else request=Checkpoints.requestRestore(id,Path.of(""),attempt);
                restorePending=true;active.mutated=true;JsonObject result=new JsonObject();result.add("restore",request);succeed(result);
            }
            case "__test_verification_config" -> {requireTest();succeed(Verification.testConfig(active.args));}
            case "__test_verification_mutate" -> {requireTest();active.initial=Observation.raw(world());active.startWorldTime=world().getTime();active.startTimeOfDay=world().getTimeOfDay();active.startSimulationIndex=simulationTicks;Observation.begin(simulationTicks,0,"verification_fault_between_ticks");active.mutated=true;Checkpoints.invalidateRest();JsonObject result=VerificationFixtures.mutate(world(),Task.string(active.args,"scenario"),Task.integer(active.args,"cycle",1,5),Task.string(active.args,"mode"),Task.string(active.args,"boundary"));for(var e:observedResult().entrySet())result.add(e.getKey(),e.getValue());succeed(result);}
            case "__test_verification_fixture" -> {
                requireTest();String scenario=Task.string(active.args,"scenario");
                Set<ChunkPos> chunks=new LinkedHashSet<>();for(int x=63;x<=65;x++)for(int z=63;z<=65;z++)chunks.add(new ChunkPos(x,z));
                prepareChunks(chunks,()->{active.initial=Observation.raw(world());active.startWorldTime=world().getTime();active.startTimeOfDay=world().getTimeOfDay();active.startSimulationIndex=simulationTicks;Observation.begin(simulationTicks,0,"verification_fixture_between_ticks");active.mutated=true;Checkpoints.invalidateRest();JsonObject result=VerificationFixtures.prepare(world(),scenario);for(var e:observedResult().entrySet())result.add(e.getKey(),e.getValue());succeed(result);});
            }
            case "__test_checkpoint_fixture", "__test_checkpoint_toggle" -> {
                requireTest();Runnable fixture=()->{
                    active.initial=Observation.raw(world());active.startWorldTime=world().getTime();active.startTimeOfDay=world().getTimeOfDay();active.startSimulationIndex=simulationTicks;
                    Observation.begin(simulationTicks,0,"test_checkpoint_between_ticks");active.mutated=true;Checkpoints.invalidateRest();
                    if(active.tool.equals("__test_checkpoint_fixture")) CheckpointFixtures.prepare(world());else CheckpointFixtures.toggle(world());succeed(observedResult());
                };
                Set<ChunkPos> chunks=new LinkedHashSet<>();for(int x=-1;x<=1;x++) for(int z=-1;z<=1;z++) chunks.add(new ChunkPos(x,z));prepareChunks(chunks,fixture);
            }
            case "__test_checkpoint_snapshot" -> {requireTest();JsonObject result=new JsonObject();result.add("checkpoint_state",checkpointSnapshot());succeed(result);}
            case "__test_checkpoint_compare" -> {
                requireTest();JsonObject expected=Checkpoints.expectedState(Task.string(active.args,"checkpoint_id")),actual=expected.deepCopy();
                JsonObject blocks=actual.getAsJsonObject("state").getAsJsonObject("blocks");JsonObject chest=blocks.getAsJsonObject("7,80,3");
                chest.getAsJsonObject("nbt").getAsJsonObject("value").getAsJsonObject("Items").getAsJsonArray("value").get(0).getAsJsonObject().getAsJsonObject("value").getAsJsonObject("count").addProperty("value",Integer.toString(Task.integer(active.args,"count",1,64)));
                JsonObject result=new JsonObject();result.add("comparison",CheckpointComparison.compare(expected,actual));succeed(result);
            }
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
            case "describe_rules" -> succeed(Rules.describe());
            case "check_geometry" -> {
                Set<ChunkPos> chunks=new LinkedHashSet<>();for(BlockPos p:RegularDoorGeometry.requiredPositions(task,active.args)) chunks.add(new ChunkPos(p));
                Runnable check=()->{active.phase="geometry_observation";succeed(RegularDoorGeometry.check(world(),task,active.args,Inputs.declared()));};
                if(chunks.stream().allMatch(c->CHUNKS.contains(c.toLong()))&&ready())check.run();else prepareChunks(chunks,check);
            }
            case "__test_geometry_entity" -> {
                requireTest();if(!ready())throw new IllegalStateException("Chunks unavailable");
                if(!active.args.has("present")||!active.args.get("present").isJsonPrimitive()||!active.args.get("present").getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("present must be boolean");
                active.mutated=true;succeed(RegularDoorGeometry.testEntity(world(),active.args.get("present").getAsBoolean()));
            }
            case "declare_input" -> {if(!ready()) throw new IllegalStateException("Chunks unavailable");succeed(Inputs.declare(world(),active.args));}
            case "prepare_input" -> {
                String mode=Task.string(active.args,"mode");Inputs.requireDeclared(world());
                Runnable prepare=()->{active.phase="adapter_preparation";active.initial=Observation.raw(world());active.startWorldTime=world().getTime();active.startTimeOfDay=world().getTimeOfDay();active.startSimulationIndex=simulationTicks;Observation.begin(simulationTicks,0,"adapter_preparation_between_ticks");JsonObject result=Inputs.prepare(world(),mode);for(var e:observedResult().entrySet()) result.add(e.getKey(),e.getValue());succeed(result);};
                prepareChunks(Inputs.chunks(),prepare);
            }
            case "modify_blocks" -> {
                active.placements=Construction.validate(world(),active.args);
                for(var p:active.placements) {Observation.track(p.pos());for(var direction:net.minecraft.util.math.Direction.values()) Observation.track(p.pos().offset(direction));}
                Set<ChunkPos> chunks=new LinkedHashSet<>();
                for(var p:active.placements) for(int dx=-1;dx<=1;dx++) for(int dz=-1;dz<=1;dz++) chunks.add(new ChunkPos(p.pos().add(dx,0,dz)));
                Runnable placement=()->{active.phase="mutation";active.initial=Observation.raw(world());active.startWorldTime=world().getTime();active.startTimeOfDay=world().getTimeOfDay();active.startSimulationIndex=simulationTicks;Observation.begin(simulationTicks,0,"mutation_between_ticks");active.mutated=true;Inputs.modified(active.placements);JsonObject result=Construction.apply(world(),active.placements,active.args.get("notify_neighbors").getAsBoolean());for(var e:observedResult().entrySet()) result.add(e.getKey(),e.getValue());succeed(result);};
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
            case "advance", "act_input", "transition" -> {
                active.requested=active.tool.equals("transition")?(active.args.has("max_ticks")?Task.integer(active.args,"max_ticks",1,Rest.MAX_TICKS):Rest.MAX_TICKS):Task.integer(active.args,"ticks",1,6000);
                if(active.args.has("trace") && (!active.args.get("trace").isJsonPrimitive() || !active.args.get("trace").getAsJsonPrimitive().isBoolean())) throw new IllegalArgumentException("trace must be a boolean");
                active.trace=active.args.has("trace") && active.args.get("trace").getAsBoolean();
                if (!ready()) {fail("infrastructure","chunks_unavailable","Simulation requires block and block-entity ticking readiness");return;}
                if(server.getPlayerManager().getCurrentPlayerCount()!=0) {fail("infrastructure","players_present","Dedicated attempts cannot contain players");return;}
                active.initial=Observation.raw(world());active.startWorldTime=world().getTime();active.startTimeOfDay=world().getTimeOfDay();active.startSimulationIndex=simulationTicks;
                if(active.args.has("interact") && (!active.args.get("interact").isJsonPrimitive() || !active.args.get("interact").getAsJsonPrimitive().isBoolean())) throw new IllegalArgumentException("interact must be boolean");
                if(active.tool.equals("act_input") || active.tool.equals("transition") && active.args.has("interact") && active.args.get("interact").getAsBoolean()) Inputs.arm(world());
                if(active.tool.equals("transition")) {active.transition=new Transition(active.initial,active.requested,RestInputs.positions(),RestInputs::expected);active.deadline=System.nanoTime()+Transition.PROCESS_TIMEOUT_SECONDS*1_000_000_000L;}
                active.phase="simulation";Observation.begin(simulationTicks+1,1,"before_world_time");active.mutated=true;
                active.simulationStartedNanos=System.nanoTime();
                if(TICK_EXECUTION.equals("sprint")) {
                    var manager=server.getTickManager();
                    if(!manager.isFrozen() || manager.isSprinting() || manager.isStepping()) throw new IllegalStateException("Simulation must start from frozen idle tick manager");
                    // startSprint's return reports a previous sprint, not success. The cached permission
                    // stays false this dispatch turn; the next real world tick begins the measured run.
                    manager.startSprint(active.requested);
                } else step();
            }
            case "read_region" -> {
                List<BlockPos> positions=Observation.region(active.args,world());Set<ChunkPos> chunks=new LinkedHashSet<>();for(var p:positions) chunks.add(new ChunkPos(p));
                Runnable read=()->{active.phase="observation";succeed(Observation.readRegion(world(),positions));};
                if(chunks.stream().allMatch(c->CHUNKS.contains(c.toLong())) && ready()) read.run();else prepareChunks(chunks,read);
            }
            case "read_artifact" -> succeed(Artifacts.read(active.args));
            case "compare_traces" -> succeed(Observation.compareTraces(active.args));
            case "__test_transition_fixture", "__test_transition_toggle" -> {
                requireTest();
                Runnable fixture=()->{
                    active.initial=Observation.raw(world());active.startWorldTime=world().getTime();active.startTimeOfDay=world().getTimeOfDay();active.startSimulationIndex=simulationTicks;
                    Observation.begin(simulationTicks,0,"test_fixture_between_ticks");active.mutated=true;
                    if(active.tool.equals("__test_transition_fixture")) TransitionFixtures.prepare(world(),Task.string(active.args,"scenario"));else TransitionFixtures.toggle(world());
                    succeed(observedResult());
                };
                if(active.tool.equals("__test_transition_fixture")) {
                    Set<ChunkPos> chunks=new LinkedHashSet<>();for(int x=63;x<=64;x++) for(int z=63;z<=64;z++) chunks.add(new ChunkPos(x,z));prepareChunks(chunks,fixture);
                } else if(!ready()) fail("infrastructure","chunks_unavailable","Fixture requires ticking-ready chunks");else fixture.run();
            }
            case "__test_transition_external_tick" -> {
                requireTest();JsonObject declared=Inputs.declared();if(declared==null) throw new IllegalArgumentException("Declared input required");
                JsonObject p=declared.getAsJsonObject("driver");BlockPos pos=new BlockPos(p.get("x").getAsInt(),p.get("y").getAsInt(),p.get("z").getAsInt());
                if(!ready()) {fail("infrastructure","chunks_unavailable","Fixture requires ticking-ready chunks");return;}
                active.initial=Observation.raw(world());active.startWorldTime=world().getTime();active.startTimeOfDay=world().getTimeOfDay();active.startSimulationIndex=simulationTicks;
                Observation.begin(simulationTicks,0,"test_fixture_between_ticks");active.mutated=true;world().scheduleBlockTick(pos,Blocks.STONE,5);succeed(observedResult());
            }
            case "__test_water_source" -> {
                requireTest();if(!ready()) throw new IllegalStateException("Chunks unavailable");
                active.initial=Observation.raw(world());active.startWorldTime=world().getTime();active.startTimeOfDay=world().getTimeOfDay();active.startSimulationIndex=simulationTicks;
                BlockPos pos=new BlockPos(1037,80,1037);Observation.track(pos);
                Observation.begin(simulationTicks,0,"test_fixture_between_ticks");active.mutated=true;
                world().setBlockState(pos,Blocks.WATER.getDefaultState(),3);succeed(observedResult());
            }
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
    private static JsonObject checkpointSnapshot() {return Checkpoints.snapshot(Observation.raw(world()),world().getTime(),world().getTimeOfDay());}
    private static JsonObject checkpointContext() {
        JsonObject result=new JsonObject();result.addProperty("format",1);result.addProperty("attempt_id",attempt);result.add("task",task.deepCopy());
        result.addProperty("simulation_ticks",simulationTicks);result.addProperty("preparation_ticks",preparationTicks);
        JsonArray chunks=new JsonArray();for(long key:CHUNKS) {ChunkPos chunk=new ChunkPos(key);JsonObject row=new JsonObject();row.addProperty("x",chunk.x);row.addProperty("z",chunk.z);chunks.add(row);}
        result.add("chunks",chunks);result.add("observation",Observation.checkpointContext());result.add("input",Inputs.checkpointContext());result.addProperty("tick_execution",TICK_EXECUTION);return result;
    }
    /** HTTP acknowledgement contains no world access; supervisor waits for this matching response marker. */
    public static void restoreResponseSent(String requestId) throws IOException {
        JsonObject marker=new JsonObject();marker.addProperty("request_id",requestId);
        CheckpointStorage.writeAtomic(Path.of("stonebench/restore-response.json"),marker);
    }
    public static ServerWorld world() {return server==null?null:server.getOverworld();}
    static void inputMutation() {active.mutated=true;}
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
        result.add("intratick_events",Observation.operationEvents());return result;
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
        server.getTickManager().stopSprinting();server.getTickManager().stopStepping();server.getTickManager().setFrozen(true);
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
        JsonObject result=new JsonObject();result.addProperty("attempt_id",attempt);result.add("task",task==null?JsonNull.INSTANCE:task.deepCopy());result.addProperty("chunks_ready",ready());result.add("input",Inputs.declared());
        result.addProperty("preparation_ticks",preparationTicks);
        result.add("restoration",restoration==null?JsonNull.INSTANCE:restoration.deepCopy());
        result.addProperty("restore_pending",restorePending);
        JsonObject environment=new JsonObject();environment.addProperty("minecraft","1.21.11");environment.addProperty("yarn","1.21.11+build.3");
        environment.addProperty("fabric_loader",FabricLoader.getInstance().getModContainer("fabricloader").orElseThrow().getMetadata().getVersion().getFriendlyString());
        environment.addProperty("controller","0.1.0");environment.addProperty("java",System.getProperty("java.version"));environment.addProperty("tick_rate",server.getTickManager().getTickRate());
        environment.addProperty("tick_execution",TICK_EXECUTION);environment.addProperty("test_initial_preparation_ticks",TEST_INITIAL_PREPARATION_TICKS);
        environment.addProperty("seed",world().getSeed());environment.addProperty("generator","flat_air");environment.addProperty("random_tick_speed",world().getGameRules().getValue(GameRules.RANDOM_TICK_SPEED));
        environment.addProperty("mob_spawning",world().getGameRules().getValue(GameRules.DO_MOB_SPAWNING));
        environment.addProperty("advance_weather",world().getGameRules().getValue(GameRules.ADVANCE_WEATHER));
        environment.addProperty("players_allowed",false);environment.addProperty("server_directory",Path.of("").toAbsolutePath().toString());
        result.add("environment",environment);return result;
    }
    private static JsonObject envelope(String status) {
        JsonObject result=new JsonObject();
        if(active.simulationStartedNanos!=0) {
            double seconds=(System.nanoTime()-active.simulationStartedNanos)/1_000_000_000.0;
            JsonObject execution=new JsonObject();execution.addProperty("mode",TICK_EXECUTION);execution.addProperty("game_ticks",active.executed);execution.addProperty("wall_seconds",seconds);execution.addProperty("measured_tps",active.executed/seconds);execution.addProperty("nominal_tick_rate",server.getTickManager().getTickRate());execution.addProperty("backend",TICK_EXECUTION.equals("sprint")?"vanilla_ServerTickManager.startSprint":"vanilla_TickManager.step(1)");
            result.add("execution",execution);
        }
        result.addProperty("operation_id",active.id);result.addProperty("operation",active.tool);result.addProperty("attempt_id",attempt);
        result.addProperty("phase",active.phase);result.addProperty("status",status);result.addProperty("ticks_executed",active.executed);
        result.addProperty("simulation_ticks",simulationTicks);result.addProperty("preparation_ticks",preparationTicks);result.addProperty("world_time",world().getTime());
        result.addProperty("preparation_initial_loaded",active.preparationInitialLoaded);result.addProperty("preparation_initial_ready",active.preparationInitialReady);
        result.addProperty("frozen",server.getTickManager().isFrozen());result.addProperty("mutated",active.mutated);
        if(artifactRecovery) {result.addProperty("artifact_recovery",true);result.addProperty("simulation_resumable",false);result.addProperty("counters_source","last_persisted_operation");}
        return result;
    }
    private static void finish(JsonObject result) {
        freeze();
        if(active.mutated && (active.transition==null || !active.transition.report().get("status").getAsString().equals("terminated"))) Checkpoints.invalidateRest();
        Inputs.stop();Observation.end();
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
        if(active.transition!=null) result.add("transition_diagnostics",active.transition.report());
        if(active.placements!=null && active.mutated) {result.add("blocks",Construction.read(world(),active.placements));result.addProperty("recovery","Inspect actual blocks; retry a validated repair lot or restore a checkpoint when checkpoint support is available");}finish(result);
    }
    public static void shutdown() {
        if(active!=null) fail("infrastructure","server_stopped","Server shutdown interrupted operation");
        Operation operation;while((operation=QUEUE.poll())!=null) {active=operation;fail("infrastructure","server_stopped","Server stopped before operation");}
        if(transport!=null) transport.close();
    }
}
