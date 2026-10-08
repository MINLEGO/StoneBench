package stonebench.prototype;

import com.google.gson.*;
import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import net.minecraft.block.*;
import net.minecraft.block.entity.*;
import net.minecraft.block.enums.BlockFace;
import net.minecraft.item.*;
import net.minecraft.nbt.*;
import net.minecraft.registry.Registries;
import net.minecraft.state.property.Properties;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.command.*;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.math.Direction;
import net.minecraft.world.tick.*;
import stonebench.prototype.mixin.*;

/** PROTOTYPE: only the seven isolated fixtures below, no production detector. */
public final class Experiment {
    private static final Gson JSON = new GsonBuilder().disableHtmlEscaping().create();
    private static final Path OUTPUT = Path.of("traces");
    private static final BlockPos LEVER = new BlockPos(1, 80, 1);
    private static final BlockPos HOPPER = new BlockPos(3, 80, 2);
    private static final BlockPos OUTPUT_CHEST = new BlockPos(4, 80, 2);
    private static final Set<String> CASES = Set.of("piston-open", "piston-close", "delayed",
        "hopper-cooldown", "hopper-locked", "hopper-empty", "clock");
    private static String phase = "idle", scenario, name;
    private static long previousTime;
    private static long loadingDeadline;
    private static int elapsed, followup, pendingTicks, movingTicks, quietPendingTicks,
        cooldownWithoutQueueTicks, changes, firstTransferTick, verificationWarmupTicks;
    private static BufferedWriter trace;
    private static JsonObject previous, endpoint, result;

    public static void register(CommandDispatcher<ServerCommandSource> dispatcher) {
        dispatcher.register(CommandManager.literal("sb").requires(source -> source.getEntity() == null)
            .then(CommandManager.literal("run")
                .then(CommandManager.argument("scenario", StringArgumentType.word())
                    .then(CommandManager.argument("name", StringArgumentType.word()).executes(ctx -> {
                        try {
                            start(ctx.getSource().getServer(), StringArgumentType.getString(ctx, "scenario"),
                                StringArgumentType.getString(ctx, "name"));
                            return 1;
                        } catch (Exception e) { fail(ctx.getSource().getServer(), e); return 0; }
                    }))))
            .then(CommandManager.literal("verify")
                .then(CommandManager.argument("name", StringArgumentType.word()).executes(ctx -> {
                    try { verify(ctx.getSource().getServer(), StringArgumentType.getString(ctx, "name")); return 1; }
                    catch (Exception e) { fail(ctx.getSource().getServer(), e); return 0; }
                }))));
    }

    private static void requireIdle(MinecraftServer server, String runName) {
        if (!phase.equals("idle") || !server.getTickManager().isFrozen()
            || server.getPlayerManager().getCurrentPlayerCount() != 0)
            throw new IllegalStateException("Requires idle, frozen server without players");
        if (!runName.matches("[a-z-]+-[123]")) throw new IllegalArgumentException("Invalid run name");
    }

    private static void start(MinecraftServer server, String fixture, String runName) throws IOException {
        requireIdle(server, runName);
        if (!CASES.contains(fixture)) throw new IllegalArgumentException("Unknown fixture");
        scenario = fixture; name = runName;
        elapsed = followup = pendingTicks = movingTicks = quietPendingTicks = cooldownWithoutQueueTicks = changes = 0;
        firstTransferTick = -1;
        ServerWorld world = server.getOverworld();
        world.setChunkForced(0, 0, true); world.getChunk(0, 0);
        phase = "loading"; previousTime = world.getTime();
        loadingDeadline = System.nanoTime() + 60_000_000_000L; step(server);
    }

    private static boolean chunkReady(ServerWorld world) {
        return world.shouldTickBlocksInChunk(0L) && world.isTickingFutureReady(0L)
            && world.getChunk(0, 0).getLevelType().isAfter(net.minecraft.server.world.ChunkLevelType.BLOCK_TICKING);
    }

    private static void prepareFixture(MinecraftServer server) {
        ServerWorld world = server.getOverworld();
        for (BlockPos pos : BlockPos.iterate(0, 79, 0, 9, 82, 5))
            world.setBlockState(pos, Blocks.AIR.getDefaultState(), Block.NOTIFY_ALL);
        for (BlockPos pos : BlockPos.iterate(0, 79, 0, 9, 79, 5))
            world.setBlockState(pos, Blocks.STONE.getDefaultState(), Block.NOTIFY_ALL);
        if (scenario.startsWith("piston") || scenario.equals("delayed")) {
            place(world, LEVER, Blocks.LEVER.getDefaultState().with(Properties.BLOCK_FACE, BlockFace.FLOOR)
                .with(Properties.HORIZONTAL_FACING, Direction.EAST));
            int repeaters = scenario.equals("delayed") ? 3 : 1;
            for (int i = 0; i < repeaters; i++)
                place(world, new BlockPos(2 + i, 80, 1), Blocks.REPEATER.getDefaultState()
                    .with(Properties.HORIZONTAL_FACING, Direction.WEST)
                    .with(Properties.DELAY, scenario.equals("delayed") ? 4 : 2));
            place(world, new BlockPos(2 + repeaters, 80, 1), Blocks.STICKY_PISTON.getDefaultState()
                .with(Properties.FACING, Direction.EAST));
            place(world, new BlockPos(3 + repeaters, 80, 1), Blocks.STONE.getDefaultState());
            if (scenario.equals("piston-close")) toggle(world);
        } else if (scenario.startsWith("hopper")) {
            place(world, OUTPUT_CHEST, Blocks.CHEST.getDefaultState());
            place(world, HOPPER, Blocks.HOPPER.getDefaultState().with(HopperBlock.FACING, Direction.EAST));
            if (scenario.equals("hopper-locked"))
                place(world, new BlockPos(2, 80, 2), Blocks.REDSTONE_BLOCK.getDefaultState());
        } else {
            place(world, new BlockPos(2, 80, 2), Blocks.OBSERVER.getDefaultState().with(Properties.FACING, Direction.EAST));
            place(world, new BlockPos(3, 80, 2), Blocks.OBSERVER.getDefaultState().with(Properties.FACING, Direction.WEST));
        }
        phase = "preparing"; elapsed = 0; previousTime = world.getTime();
        if (!server.getTickManager().step(20)) throw new IllegalStateException("Cannot prepare");
    }

    private static void place(ServerWorld world, BlockPos pos, BlockState state) {
        world.setBlockState(pos, state, Block.NOTIFY_ALL);
    }

    private static void toggle(ServerWorld world) {
        BlockState state = world.getBlockState(LEVER);
        ((LeverBlock) state.getBlock()).togglePower(state, world, LEVER, null);
    }

    private static void begin(MinecraftServer server) throws IOException {
        ServerWorld world = server.getOverworld();
        if (scenario.startsWith("piston")) {
            boolean extended = world.getBlockState(new BlockPos(3, 80, 1)).get(PistonBlock.EXTENDED);
            if (extended != scenario.equals("piston-close")) throw new IllegalStateException("Invalid initial piston");
        }
        if (scenario.startsWith("piston") || scenario.equals("delayed")) toggle(world);
        if (scenario.equals("hopper-cooldown")) {
            HopperBlockEntity hopper = (HopperBlockEntity) world.getBlockEntity(HOPPER);
            hopper.setStack(0, new ItemStack(Items.DIAMOND, 3));
            ((HopperAccess) hopper).transitionCooldown(8);
            hopper.markDirty();
        }
        if (scenario.startsWith("hopper")) {
            boolean enabled = world.getBlockState(HOPPER).get(HopperBlock.ENABLED);
            if (enabled == scenario.equals("hopper-locked")) throw new IllegalStateException("Invalid hopper lock");
        }
        Files.createDirectories(OUTPUT);
        trace = Files.newBufferedWriter(OUTPUT.resolve(name + ".jsonl"), StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
        elapsed = 0; phase = "detecting";
        previous = snapshot(world);
        writeObservation(previous, "input", "awaiting-first-tick", true);
        step(server);
    }

    private static boolean queuesEmpty(JsonObject state) {
        for (String field : List.of("blockTicks", "fluidTicks", "blockEvents"))
            if (!state.getAsJsonArray(field).isEmpty()) return false;
        return true;
    }

    // World clocks are recorded separately; no internal NBT/runtime fields are removed.
    private static JsonObject relevant(JsonObject state) {
        JsonObject value = state.deepCopy(); value.remove("worldTime"); value.remove("timeOfDay"); return value;
    }

    private static boolean sameBlockStates(JsonObject a, JsonObject b) {
        JsonArray left = a.getAsJsonArray("blocks"), right = b.getAsJsonArray("blocks");
        for (int i = 0; i < left.size(); i++)
            if (!left.get(i).getAsJsonObject().get("state").equals(right.get(i).getAsJsonObject().get("state"))) return false;
        return true;
    }

    private static String activity(ServerWorld world, JsonObject current) {
        if (!queuesEmpty(current)) return "pending-events";
        boolean hopperPresent = false;
        for (BlockPos pos : BlockPos.iterate(0, 79, 0, 9, 82, 5)) {
            BlockEntity entity = world.getBlockEntity(pos);
            if (entity instanceof PistonBlockEntity || world.getBlockState(pos).isOf(Blocks.MOVING_PISTON)) return "moving-piston";
            if (entity instanceof HopperBlockEntity hopper) {
                hopperPresent = true;
                if (((HopperAccess) hopper).transitionCooldown() > 0) return "hopper-cooldown";
                if (world.getBlockState(pos).get(HopperBlock.ENABLED) && !hopper.isEmpty()) return "hopper-transfer-possible";
            } else if (entity != null && !(entity instanceof ChestBlockEntity)) return "unknown-block-entity";
        }
        // shortcut: strict internal-state equality cannot certify ticking hoppers; broaden only with a differential experiment.
        if (hopperPresent) return "hopper-lastTickTime-keeps-changing";
        if (!relevant(previous).equals(relevant(current))) return "state-changed";
        return "quiescent";
    }

    public static void afterTick(MinecraftServer server) {
        if (phase.equals("idle")) return;
        try {
            ServerWorld world = server.getOverworld();
            long time = world.getTime();
            if (time == previousTime) return;
            if (time != previousTime + 1) throw new IllegalStateException("Skipped world tick");
            previousTime = time; elapsed++;
            if (phase.equals("loading")) {
                if (chunkReady(world)) prepareFixture(server);
                else if (System.nanoTime() >= loadingDeadline) throw readinessError(world);
                else step(server);
                return;
            }
            if (phase.equals("verify-loading")) {
                if (!relevant(endpoint).equals(relevant(snapshot(world))))
                    throw new IllegalStateException("Restored endpoint changed while waiting for tick-ready chunk");
                if (chunkReady(world)) beginVerification(server);
                else if (System.nanoTime() >= loadingDeadline) throw readinessError(world);
                else step(server);
                return;
            }
            if (!chunkReady(world)) throw new IllegalStateException("Observed chunk stopped ticking");
            if (phase.equals("preparing")) { if (elapsed == 20) begin(server); return; }
            JsonObject current = snapshot(world);
            if (phase.equals("verifying")) {
                if (!relevant(endpoint).equals(relevant(current)))
                    throw new IllegalStateException("Endpoint changed in restored copy at followup tick " + elapsed);
                writeObservation(current, "verification", "unchanged", false);
                if (elapsed == 200) {
                    trace.close(); trace = null; phase = "idle";
                    JsonObject verified = new JsonObject(); verified.addProperty("success", true);
                    verified.addProperty("ticks", elapsed);
                    verified.addProperty("warmupTicks", verificationWarmupTicks);
                    Files.writeString(OUTPUT.resolve(name + ".verification.json"), JSON.toJson(verified));
                    marker(name + ".verified");
                } else step(server);
            } else if (phase.equals("diagnostic")) {
                writeObservation(current, "diagnostic", "indeterminate-followup", false);
                if (++followup == 200) finish(); else step(server);
            } else {
                String reason = activity(world, current);
                if (!queuesEmpty(current)) pendingTicks++;
                if (sameBlockStates(previous, current) && !queuesEmpty(current)) quietPendingTicks++;
                for (BlockPos pos : BlockPos.iterate(0, 79, 0, 9, 82, 5))
                    if (world.getBlockEntity(pos) instanceof PistonBlockEntity) { movingTicks++; break; }
                if (!previous.get("blocks").equals(current.get("blocks"))) changes++;
                if (scenario.equals("hopper-cooldown")) {
                    HopperAccess hopper = (HopperAccess) world.getBlockEntity(HOPPER);
                    if (hopper.transitionCooldown() > 0 && queuesEmpty(current)) cooldownWithoutQueueTicks++;
                    ChestBlockEntity chest = (ChestBlockEntity) world.getBlockEntity(OUTPUT_CHEST);
                    if (!chest.isEmpty() && firstTransferTick < 0) firstTransferTick = elapsed;
                }
                writeObservation(current, "tick", reason, false);
                if (reason.equals("quiescent")) decide("terminated", reason, current);
                else if (reason.equals("hopper-lastTickTime-keeps-changing") || reason.equals("unknown-block-entity"))
                    decide("indeterminate", reason, current);
                else if (elapsed == 36000) decide("limit-reached", reason, current);
                if (phase.equals("diagnostic")) step(server);
                else if (phase.equals("detecting")) step(server);
            }
            previous = current;
        } catch (Exception e) { fail(server, e); }
    }

    private static void decide(String status, String reason, JsonObject state) throws IOException {
        result = new JsonObject(); result.addProperty("scenario", scenario); result.addProperty("name", name);
        result.addProperty("status", status); result.addProperty("reason", reason); result.addProperty("tick", elapsed);
        result.addProperty("pendingTicks", pendingTicks); result.addProperty("movingTicks", movingTicks);
        result.addProperty("quietWithPendingTicks", quietPendingTicks);
        result.addProperty("cooldownWithoutQueueTicks", cooldownWithoutQueueTicks);
        result.addProperty("stateChanges", changes); result.addProperty("firstTransferTick", firstTransferTick);
        result.add("endpoint", state);
        if (status.equals("indeterminate")) phase = "diagnostic";
        else finish();
    }

    private static void finish() throws IOException {
        result.addProperty("diagnosticTicks", followup);
        Files.writeString(OUTPUT.resolve(name + ".result.json"), JSON.toJson(result));
        trace.close(); trace = null; phase = "idle"; marker(name + ".done");
    }

    private static void verify(MinecraftServer server, String runName) throws IOException {
        requireIdle(server, runName); name = runName;
        result = JsonParser.parseString(Files.readString(OUTPUT.resolve(name + ".result.json"))).getAsJsonObject();
        if (!result.get("status").getAsString().equals("terminated")) throw new IllegalStateException("Cannot verify non-endpoint");
        endpoint = result.getAsJsonObject("endpoint");
        ServerWorld world = server.getOverworld(); world.setChunkForced(0, 0, true); world.getChunk(0, 0);
        previous = snapshot(world);
        if (!relevant(endpoint).equals(relevant(previous))) throw new IllegalStateException("Restored endpoint differs before first tick");
        phase = "verify-loading"; elapsed = 0; previousTime = world.getTime();
        loadingDeadline = System.nanoTime() + 60_000_000_000L; step(server);
    }

    private static void beginVerification(MinecraftServer server) throws IOException {
        ServerWorld world = server.getOverworld();
        verificationWarmupTicks = elapsed;
        previous = snapshot(world);
        trace = Files.newBufferedWriter(OUTPUT.resolve(name + ".verification.jsonl"), StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
        phase = "verifying"; elapsed = 0; previousTime = world.getTime();
        writeObservation(previous, "restored", "unchanged", true); step(server);
    }

    private static void step(MinecraftServer server) {
        if (!server.getTickManager().step(1)) throw new IllegalStateException("Cannot advance exactly one tick");
    }

    private static IllegalStateException readinessError(ServerWorld world) {
        return new IllegalStateException("Chunk readiness timeout: blocks=" + world.shouldTickBlocksInChunk(0L)
            + ", future=" + world.isTickingFutureReady(0L)
            + ", level=" + world.getChunk(0, 0).getLevelType());
    }

    private static void writeObservation(JsonObject current, String event, String reason, boolean full) throws IOException {
        JsonObject row = new JsonObject(); row.addProperty("tick", elapsed); row.addProperty("event", event);
        row.addProperty("reason", reason); row.addProperty("worldTime", current.get("worldTime").getAsLong());
        row.add("timeOfDay", current.get("timeOfDay")); row.addProperty("blockStatesUnchanged", sameBlockStates(previous, current));
        row.addProperty("relevantStateUnchanged", relevant(previous).equals(relevant(current)));
        JsonArray blocks = new JsonArray(); JsonArray all = current.getAsJsonArray("blocks");
        for (int i = 0; i < all.size(); i++)
            if (full || !all.get(i).equals(previous.getAsJsonArray("blocks").get(i))) blocks.add(all.get(i));
        row.add(full ? "blocks" : "changedBlocks", blocks);
        for (String field : List.of("blockTicks", "fluidTicks", "blockEvents")) row.add(field, current.get(field));
        trace.write(JSON.toJson(row)); trace.newLine();
    }

    public static void ready() {
        try { marker("boot-" + System.getProperty("stonebench.boot") + ".ready"); }
        catch (IOException e) { throw new UncheckedIOException(e); }
    }

    private static void marker(String file) throws IOException {
        Files.createDirectories(OUTPUT); Files.writeString(OUTPUT.resolve(file), "ok\n");
    }

    private static void fail(MinecraftServer server, Exception error) {
        server.getTickManager().stopStepping(); phase = "idle"; error.printStackTrace();
        try {
            if (trace != null) { trace.close(); trace = null; }
            Files.createDirectories(OUTPUT); Files.writeString(OUTPUT.resolve("error.txt"), error.toString());
        } catch (IOException writingError) { writingError.printStackTrace(); }
    }
    private static boolean inside(BlockPos p) {
        return p.getX() >= 0 && p.getX() <= 9 && p.getY() >= 79 && p.getY() <= 82
            && p.getZ() >= 0 && p.getZ() <= 5;
    }

    private static JsonArray position(BlockPos p) {
        JsonArray a = new JsonArray(); a.add(p.getX()); a.add(p.getY()); a.add(p.getZ()); return a;
    }

    // Preserve NBT types and list order; sort only unordered compound keys.
    private static JsonElement nbt(NbtElement value) {
        JsonObject result = new JsonObject(); result.addProperty("type", value.getType());
        if (value instanceof NbtCompound compound) {
            JsonObject entries = new JsonObject();
            compound.getKeys().stream().sorted().forEach(key -> entries.add(key, nbt(compound.get(key))));
            result.add("value", entries);
        } else if (value instanceof NbtList list) {
            JsonArray entries = new JsonArray(); list.forEach(item -> entries.add(nbt(item)));
            result.add("value", entries);
        } else result.addProperty("value", value.toString());
        return result;
    }

    @SuppressWarnings("unchecked")
    private static <T> JsonArray ticks(WorldTickScheduler<T> scheduler) {
        JsonArray result = new JsonArray();
        List<OrderedTick<T>> all = new ArrayList<>();
        ((SchedulerAccess<T>) scheduler).checkpointSchedulers().values().forEach(chunk ->
            chunk.getQueueAsStream().filter(t -> inside(t.pos())).forEach(all::add));
        all.sort(Comparator.comparingLong(OrderedTick<T>::triggerTick)
            .thenComparingInt(t -> t.priority().getIndex()).thenComparingLong(OrderedTick<T>::subTickOrder));
        for (OrderedTick<T> tick : all) {
            JsonObject t = new JsonObject();
            t.add("pos", position(tick.pos()));
            Object type = tick.type();
            t.addProperty("type", type instanceof Block b ? Registries.BLOCK.getId(b).toString()
                : Registries.FLUID.getId((net.minecraft.fluid.Fluid) type).toString());
            t.addProperty("triggerTick", tick.triggerTick());
            t.addProperty("priority", tick.priority().getIndex());
            t.addProperty("subTickOrder", tick.subTickOrder());
            result.add(t);
        }
        return result;
    }

    private static JsonObject snapshot(ServerWorld world) {
        JsonObject result = new JsonObject();
        result.addProperty("worldTime", world.getTime());
        result.addProperty("timeOfDay", world.getTimeOfDay());
        JsonArray blocks = new JsonArray();
        for (int x = 0; x <= 9; x++) for (int y = 79; y <= 82; y++) for (int z = 0; z <= 5; z++) {
            BlockPos p = new BlockPos(x, y, z);
            JsonObject b = new JsonObject(); b.add("pos", position(p));
            b.addProperty("state", world.getBlockState(p).toString());
            BlockEntity entity = world.getBlockEntity(p);
            if (entity != null) b.add("nbt", nbt(entity.createNbtWithIdentifyingData(world.getRegistryManager())));
            if (entity instanceof HopperBlockEntity hopper) {
                HopperAccess access = (HopperAccess) hopper;
                JsonObject runtime = new JsonObject();
                runtime.addProperty("lastTickTime", access.transitionLastTickTime());
                runtime.addProperty("transferCooldown", access.transitionCooldown());
                b.add("runtime", runtime);
            }
            blocks.add(b);
        }
        result.add("blocks", blocks);
        result.add("blockTicks", ticks(world.getBlockTickScheduler()));
        result.add("fluidTicks", ticks(world.getFluidTickScheduler()));
        JsonArray events = new JsonArray();
        for (var event : ((WorldAccess) world).checkpointEvents()) {
            if (!inside(event.pos())) continue;
            JsonObject e = new JsonObject(); e.add("pos", position(event.pos()));
            e.addProperty("block", Registries.BLOCK.getId(event.block()).toString());
            e.addProperty("type", event.type()); e.addProperty("data", event.data()); events.add(e);
        }
        result.add("blockEvents", events);
        return result;
    }



}
