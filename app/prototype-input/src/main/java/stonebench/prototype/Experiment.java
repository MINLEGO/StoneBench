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
import net.minecraft.util.math.Vec3d;
import net.minecraft.util.Hand;
import net.minecraft.util.hit.BlockHitResult;
import net.minecraft.world.tick.*;
import stonebench.prototype.mixin.*;

/** PROTOTYPE: four fixed fixtures, no production input API or general stability detector. */
public final class Experiment {
    private static final Gson JSON = new GsonBuilder().disableHtmlEscaping().create();
    private static final Path OUTPUT = Path.of("traces");
    private static final BlockPos INPUT = new BlockPos(4, 80, 2);
    private static final BlockPos COMPONENT = new BlockPos(5, 80, 2);
    private static final BlockPos EXTERNAL = new BlockPos(3, 80, 2);
    private static final Set<String> FIXTURES = Set.of("torch", "repeater-1", "repeater-4", "piston");
    private static String phase = "idle", fixture, device, mode, name;
    private static BlockPos driver;
    private static int simulationTick, warmup, ticks;
    private static long previousTime, deadline;
    private static boolean armed, beforeIncrement, sourcePowered, inputPowered;
    private static String componentState;
    private static BufferedWriter trace;
    private static JsonObject baseline, previous, opened;
    private static JsonArray events;

    public static void register(CommandDispatcher<ServerCommandSource> dispatcher) {
        dispatcher.register(CommandManager.literal("sb").requires(source -> source.getEntity() == null)
            .then(CommandManager.literal("prepare").then(CommandManager.argument("fixture", StringArgumentType.word())
                .executes(ctx -> { try { prepare(ctx.getSource().getServer(), StringArgumentType.getString(ctx, "fixture")); return 1; }
                    catch (Exception e) { fail(ctx.getSource().getServer(), e); return 0; } })))
            .then(CommandManager.literal("run")
                .then(CommandManager.argument("fixture", StringArgumentType.word())
                .then(CommandManager.argument("device", StringArgumentType.word())
                .then(CommandManager.argument("mode", StringArgumentType.word())
                .then(CommandManager.argument("name", StringArgumentType.word()).executes(ctx -> {
                    try { run(ctx.getSource().getServer(), StringArgumentType.getString(ctx, "fixture"),
                        StringArgumentType.getString(ctx, "device"), StringArgumentType.getString(ctx, "mode"),
                        StringArgumentType.getString(ctx, "name")); return 1; }
                    catch (Exception e) { fail(ctx.getSource().getServer(), e); return 0; }
                })))))));
    }

    private static void requireIdle(MinecraftServer server, String selected) {
        if (!phase.equals("idle") || !server.getTickManager().isFrozen()
            || server.getPlayerManager().getCurrentPlayerCount() != 0) throw new IllegalStateException("Requires frozen, idle server without players");
        if (!FIXTURES.contains(selected)) throw new IllegalArgumentException("Unknown fixture");
        fixture = selected; simulationTick = -1; warmup = ticks = 0;
        ServerWorld world = server.getOverworld();
        world.setChunkForced(0, 0, true); world.getChunk(0, 0);
        previousTime = world.getTime(); deadline = System.nanoTime() + 60_000_000_000L;
    }

    private static void prepare(MinecraftServer server, String selected) {
        requireIdle(server, selected); phase = "loading-checkpoint"; step(server);
    }

    private static void fixture(ServerWorld world) {
        for (BlockPos p : BlockPos.iterate(0, 79, 0, 10, 82, 5)) place(world, p, Blocks.AIR.getDefaultState());
        for (BlockPos p : BlockPos.iterate(0, 79, 0, 10, 79, 5)) place(world, p, Blocks.STONE.getDefaultState());
        place(world, INPUT, Blocks.STONE.getDefaultState());
        if (fixture.startsWith("repeater")) {
            place(world, COMPONENT, Blocks.REPEATER.getDefaultState().with(Properties.HORIZONTAL_FACING, Direction.WEST)
                .with(Properties.DELAY, fixture.endsWith("4") ? 4 : 1));
        } else {
            place(world, COMPONENT, Blocks.REDSTONE_WALL_TORCH.getDefaultState().with(Properties.HORIZONTAL_FACING, Direction.EAST));
        }
        if (fixture.equals("piston")) {
            place(world, new BlockPos(7, 80, 2), Blocks.STICKY_PISTON.getDefaultState().with(Properties.FACING, Direction.EAST));
            place(world, new BlockPos(8, 80, 2), Blocks.STONE.getDefaultState());
            BlockPos wire = new BlockPos(6, 80, 2);
            // Default wire state is an unconnected dot; use vanilla placement after its neighbors exist.
            ItemPlacementContext context = new ItemPlacementContext(world, null, Hand.MAIN_HAND, new ItemStack(Items.REDSTONE),
                new BlockHitResult(Vec3d.ofCenter(wire.down()).add(0, 0.5, 0), Direction.UP, wire.down(), false)) {};
            place(world, wire, Blocks.REDSTONE_WIRE.getPlacementState(context));
        }
        BlockPos chest = new BlockPos(5, 80, 4);
        place(world, chest, Blocks.CHEST.getDefaultState());
        ChestBlockEntity entity = (ChestBlockEntity) world.getBlockEntity(chest);
        entity.setStack(0, new ItemStack(Items.DIAMOND, 7)); entity.markDirty();
        phase = "settling-checkpoint"; ticks = 0;
    }

    private static void run(MinecraftServer server, String selected, String selectedDevice, String selectedMode, String runName) throws IOException {
        requireIdle(server, selected);
        if (!Set.of("lever", "stone-button", "wood-button").contains(selectedDevice)
            || !Set.of("direct", "repeater").contains(selectedMode) || !runName.matches("[a-z0-9-]+"))
            throw new IllegalArgumentException("Invalid input case");
        device = selectedDevice; mode = selectedMode; name = runName;
        baseline = JsonParser.parseString(Files.readString(OUTPUT.resolve(fixture + ".checkpoint.json"))).getAsJsonObject();
        JsonObject restored = snapshot(server.getOverworld());
        if (!baseline.equals(restored)) throw new IllegalStateException("Checkpoint differs before first world tick");
        phase = "loading-run"; step(server);
    }

    private static void adapter(ServerWorld world) {
        driver = mode.equals("direct") ? EXTERNAL : new BlockPos(1, 80, 2);
        if (mode.equals("repeater")) {
            place(world, new BlockPos(2, 80, 2), Blocks.STONE.getDefaultState());
            place(world, EXTERNAL, Blocks.REPEATER.getDefaultState().with(Properties.HORIZONTAL_FACING, Direction.WEST).with(Properties.DELAY, 1));
        }
        Block block = device.equals("lever") ? Blocks.LEVER : device.equals("stone-button") ? Blocks.STONE_BUTTON : Blocks.OAK_BUTTON;
        place(world, driver, block.getDefaultState().with(Properties.BLOCK_FACE, BlockFace.WALL).with(Properties.HORIZONTAL_FACING, Direction.WEST));
        phase = "settling-adapter"; ticks = 0;
    }

    private static void begin(ServerWorld world) throws IOException {
        previous = snapshot(world);
        if (!common(baseline).equals(common(previous)) || !idle(world, previous, false) || world.getReceivedRedstonePower(INPUT) != 0)
            throw new IllegalStateException("Adapter preparation changed construction state 0");
        trace = Files.newBufferedWriter(OUTPUT.resolve(name + ".jsonl"), StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
        events = new JsonArray(); opened = null;
        sourcePowered = inputPowered = false; componentState = world.getBlockState(COMPONENT).toString();
        simulationTick = -1; armed = true; phase = "running";
        observation(world, "initial");
    }

    public static void beforeTime(ServerWorld world) {
        if (phase.equals("idle") || world != world.getServer().getOverworld()) return;
        simulationTick++;
        if (!phase.equals("running") || !armed) return;
        try {
            beforeIncrement = true; armed = false;
            BlockState state = world.getBlockState(driver);
            if (state.getBlock() instanceof LeverBlock lever) lever.togglePower(state, world, driver, null);
            else ((ButtonBlock) state.getBlock()).powerOn(state, world, driver, null);
            observation(world, "after-input-before-time-increment");
        } catch (Exception e) { fail(world.getServer(), e); }
        finally { beforeIncrement = false; }
    }

    public static void changed(ServerWorld world, BlockPos pos) {
        if (!phase.equals("running") || world != world.getServer().getOverworld() || !inside(pos)) return;
        if (pos.equals(driver)) {
            boolean powered = world.getBlockState(driver).get(Properties.POWERED);
            if (powered != sourcePowered) { sourcePowered = powered; event(world, "source", powered, null); }
        }
        boolean powered = world.getReceivedRedstonePower(INPUT) > 0;
        if (powered != inputPowered) { inputPowered = powered; event(world, "input", powered, null); }
        String state = world.getBlockState(COMPONENT).toString();
        if (!state.equals(componentState)) { componentState = state; event(world, "component", null, state); }
    }

    private static void event(ServerWorld world, String kind, Boolean powered, String state) {
        JsonObject event = new JsonObject(); event.addProperty("kind", kind); event.addProperty("tick", simulationTick);
        event.addProperty("worldTime", world.getTime());
        event.addProperty("phase", beforeIncrement ? "before-time-increment" : "world-tick");
        if (powered != null) event.addProperty("powered", powered);
        if (state != null) event.addProperty("state", state);
        events.add(event);
    }

    public static void afterTick(MinecraftServer server) {
        if (phase.equals("idle")) return;
        try {
            ServerWorld world = server.getOverworld(); long time = world.getTime();
            if (time == previousTime) return;
            if (time != previousTime + 1) throw new IllegalStateException("Skipped world tick");
            previousTime = time; ticks++;
            if (phase.startsWith("loading")) {
                if (phase.equals("loading-run") && !common(baseline).equals(common(snapshot(world))))
                    throw new IllegalStateException("Construction changed during checkpoint loading");
                if (ready(world)) { if (phase.equals("loading-checkpoint")) fixture(world); else adapter(world); }
                else if (System.nanoTime() >= deadline) throw new IllegalStateException("Chunk readiness timeout");
            } else if (!ready(world)) throw new IllegalStateException("Chunk stopped ticking");
            else if (phase.equals("settling-checkpoint") && ticks >= 20) {
                JsonObject state = snapshot(world);
                if (!idle(world, state, false)) throw new IllegalStateException("Fixture not at rest");
                Files.writeString(OUTPUT.resolve(fixture + ".checkpoint.json"), JSON.toJson(state));
                phase = "idle"; marker(fixture + ".prepared"); return;
            } else if (phase.equals("settling-adapter") && ticks >= 20) { warmup = simulationTick + 1; begin(world); }
            else if (phase.equals("running")) {
                JsonObject current = snapshot(world);
                boolean commonIdle = idle(world, current, true) && common(previous).equals(common(current));
                if (opened == null && inputPowered && commonIdle) {
                    opened = current.deepCopy(); observation(world, "open-endpoint");
                    if (device.equals("lever")) armed = true;
                }
                observation(world, "tick");
                if (opened != null && !inputPowered && !sourcePowered && idle(world, current, false)
                    && relevant(previous).equals(relevant(current))) {
                    observation(world, "closed-endpoint"); finish(world, current); return;
                }
                int lastEdge = events.asList().stream().filter(e -> e.getAsJsonObject().get("kind").getAsString().equals("input"))
                    .mapToInt(e -> e.getAsJsonObject().get("tick").getAsInt()).max().orElse(0);
                if (simulationTick - lastEdge >= 36000) throw new IllegalStateException("Transition reached 36000 ticks");
                previous = current;
            }
            step(server);
        } catch (Exception e) { fail(server, e); }
    }

    private static void finish(ServerWorld world, JsonObject closed) throws IOException {
        JsonObject result = new JsonObject();
        result.addProperty("name", name); result.addProperty("fixture", fixture); result.addProperty("device", device); result.addProperty("mode", mode);
        result.addProperty("status", "terminated"); result.addProperty("lastTick", simulationTick); result.addProperty("warmupTicks", warmup);
        result.add("initial", common(baseline)); result.add("opened", common(opened)); result.add("closed", common(closed)); result.add("events", events);
        result.addProperty("returnedToState0", common(baseline).equals(common(closed)));
        Files.writeString(OUTPUT.resolve(name + ".result.json"), JSON.toJson(result));
        trace.close(); trace = null; phase = "idle"; marker(name + ".done");
    }

    private static boolean ready(ServerWorld world) {
        return world.shouldTickBlocksInChunk(0L) && world.isTickingFutureReady(0L)
            && world.getChunk(0, 0).getLevelType().isAfter(net.minecraft.server.world.ChunkLevelType.BLOCK_TICKING);
    }

    private static boolean idle(ServerWorld world, JsonObject state, boolean commonOnly) {
        for (String field : List.of("blockTicks", "fluidTicks", "blockEvents"))
            for (JsonElement event : state.getAsJsonArray(field))
                if (!commonOnly || event.getAsJsonObject().getAsJsonArray("pos").get(0).getAsInt() >= 4) return false;
        for (BlockPos p : BlockPos.iterate(4, 79, 0, 10, 82, 5)) {
            if (world.getBlockState(p).isOf(Blocks.MOVING_PISTON) || world.getBlockEntity(p) instanceof PistonBlockEntity) return false;
            if (world.getBlockEntity(p) != null && !(world.getBlockEntity(p) instanceof ChestBlockEntity)) return false;
        }
        return true;
    }

    private static JsonObject relevant(JsonObject state) {
        JsonObject copy = state.deepCopy(); copy.remove("worldTime"); copy.remove("timeOfDay"); return copy;
    }

    private static JsonObject common(JsonObject state) {
        JsonObject copy = relevant(state); copy.remove("adapter");
        for (String field : List.of("blockTicks", "fluidTicks", "blockEvents")) {
            JsonArray filtered = new JsonArray();
            for (JsonElement e : copy.getAsJsonArray(field)) if (e.getAsJsonObject().getAsJsonArray("pos").get(0).getAsInt() >= 4) filtered.add(e);
            copy.add(field, filtered);
        }
        return copy;
    }

    private static void observation(ServerWorld world, String event) throws IOException {
        JsonObject row = new JsonObject(); row.addProperty("tick", simulationTick); row.addProperty("event", event);
        row.addProperty("phase", beforeIncrement ? "before-time-increment" : "after-world-tick");
        row.addProperty("sourcePowered", sourcePowered); row.addProperty("inputPowered", inputPowered);
        row.add("state", snapshot(world));
        trace.write(JSON.toJson(row)); trace.newLine();
    }

    private static void place(ServerWorld world, BlockPos pos, BlockState state) { world.setBlockState(pos, state, Block.NOTIFY_ALL); }
    private static void step(MinecraftServer server) { if (!server.getTickManager().step(1)) throw new IllegalStateException("Cannot advance one tick"); }
    public static void ready() { try { marker("boot-" + System.getProperty("stonebench.boot") + ".ready"); } catch (IOException e) { throw new UncheckedIOException(e); } }
    private static void marker(String file) throws IOException { Files.createDirectories(OUTPUT); Files.writeString(OUTPUT.resolve(file), "ok\n"); }
    private static void fail(MinecraftServer server, Exception error) {
        server.getTickManager().stopStepping(); phase = "idle"; error.printStackTrace();
        try { if (trace != null) { trace.close(); trace = null; } Files.createDirectories(OUTPUT); Files.writeString(OUTPUT.resolve("error.txt"), error.toString()); }
        catch (IOException e) { e.printStackTrace(); }
    }
    private static boolean inside(BlockPos p) { return p.getX() >= 0 && p.getX() <= 10 && p.getY() >= 79 && p.getY() <= 82 && p.getZ() >= 0 && p.getZ() <= 5; }

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
        JsonArray blocks = new JsonArray(); JsonArray adapter = new JsonArray();
        for (int x = 0; x <= 10; x++) for (int y = 79; y <= 82; y++) for (int z = 0; z <= 5; z++) {
            BlockPos p = new BlockPos(x, y, z);
            JsonObject b = new JsonObject(); b.add("pos", position(p));
            b.addProperty("state", world.getBlockState(p).toString());
            BlockEntity entity = world.getBlockEntity(p);
            if (entity != null) b.add("nbt", nbt(entity.createNbtWithIdentifyingData(world.getRegistryManager())));
            if (x >= 4) blocks.add(b); else adapter.add(b);
        }
        result.add("blocks", blocks); result.add("adapter", adapter);
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
