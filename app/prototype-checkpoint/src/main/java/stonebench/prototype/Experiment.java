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
import net.minecraft.item.*;
import net.minecraft.nbt.*;
import net.minecraft.registry.Registries;
import net.minecraft.block.enums.BlockFace;
import net.minecraft.state.property.Properties;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.command.*;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.math.Direction;
import net.minecraft.world.tick.*;
import stonebench.prototype.mixin.*;

/** Throwaway experiment: fixed fixture, fixed input, no production API. */
public final class Experiment {
    private static final Gson JSON = new GsonBuilder().disableHtmlEscaping().create();
    private static final BlockPos LEVER = new BlockPos(1, 80, 1);
    private static final BlockPos PISTON = new BlockPos(3, 80, 1);
    private static final BlockPos CHEST = new BlockPos(7, 80, 3);
    private static final Path OUTPUT = Path.of("traces");
    private static String phase = "idle";
    private static String run;
    private static long previousTime;
    private static int elapsed;
    private static BufferedWriter trace;

    public static void register(CommandDispatcher<ServerCommandSource> dispatcher) {
        dispatcher.register(CommandManager.literal("sb")
            .requires(source -> source.getEntity() == null)
            .then(CommandManager.literal("prepare").executes(ctx -> {
                try { prepare(ctx.getSource().getServer()); return 1; }
                catch (Exception e) { fail(e); return 0; }
            }))
            .then(CommandManager.literal("record")
                .then(CommandManager.argument("name", StringArgumentType.word()).executes(ctx -> {
                    try {
                        start(ctx.getSource().getServer(), StringArgumentType.getString(ctx, "name"));
                        return 1;
                    } catch (Exception e) { fail(e); return 0; }
                }))));
    }

    private static void prepare(MinecraftServer server) throws IOException {
        requireIdle(server);
        ServerWorld world = server.getOverworld();
        world.setChunkForced(0, 0, true);
        world.getChunk(0, 0);
        for (BlockPos p : BlockPos.iterate(0, 79, 0, 9, 82, 5))
            world.setBlockState(p, Blocks.AIR.getDefaultState(), Block.NOTIFY_ALL);
        for (BlockPos p : BlockPos.iterate(0, 79, 0, 9, 79, 5))
            world.setBlockState(p, Blocks.STONE.getDefaultState(), Block.NOTIFY_ALL);
        world.setBlockState(LEVER, Blocks.LEVER.getDefaultState()
            .with(Properties.BLOCK_FACE, BlockFace.FLOOR).with(Properties.HORIZONTAL_FACING, Direction.EAST), Block.NOTIFY_ALL);
        world.setBlockState(new BlockPos(2, 80, 1), Blocks.REPEATER.getDefaultState()
            .with(Properties.HORIZONTAL_FACING, Direction.WEST).with(Properties.DELAY, 2), Block.NOTIFY_ALL);
        world.setBlockState(PISTON, Blocks.STICKY_PISTON.getDefaultState()
            .with(Properties.FACING, Direction.EAST), Block.NOTIFY_ALL);
        world.setBlockState(new BlockPos(4, 80, 1), Blocks.STONE.getDefaultState(), Block.NOTIFY_ALL);
        world.setBlockState(CHEST, Blocks.CHEST.getDefaultState(), Block.NOTIFY_ALL);
        ChestBlockEntity chest = (ChestBlockEntity) world.getBlockEntity(CHEST);
        chest.setStack(0, new ItemStack(Items.DIAMOND, 7));
        chest.markDirty();
        phase = "settling";
        previousTime = world.getTime();
        elapsed = 0;
        if (!server.getTickManager().step(20)) throw new IllegalStateException("Cannot step frozen server");
    }

    private static void requireIdle(MinecraftServer server) {
        if (!phase.equals("idle") || !server.getTickManager().isFrozen()
            || server.getPlayerManager().getCurrentPlayerCount() != 0)
            throw new IllegalStateException("Experiment requires idle, frozen server with no players");
    }

    private static void start(MinecraftServer server, String name) throws IOException {
        requireIdle(server);
        if (!name.matches("reference|replay-[123]")) throw new IllegalArgumentException("Invalid run name");
        assertRest(server.getOverworld());
        run = name;
        Files.createDirectories(OUTPUT);
        trace = Files.newBufferedWriter(OUTPUT.resolve(run + ".jsonl"), StandardCharsets.UTF_8,
            StandardOpenOption.CREATE_NEW);
        elapsed = 0;
        previousTime = server.getOverworld().getTime();
        record(server.getOverworld(), "initial");
        toggle(server.getOverworld());
        record(server.getOverworld(), "input-on");
        phase = "running";
        if (!server.getTickManager().step(40)) throw new IllegalStateException("Cannot step");
    }

    private static void toggle(ServerWorld world) {
        BlockState state = world.getBlockState(LEVER);
        ((LeverBlock) state.getBlock()).togglePower(state, world, LEVER, null);
    }

    public static void afterTick(MinecraftServer server) {
        if (phase.equals("idle")) return;
        try {
            ServerWorld world = server.getOverworld();
            long time = world.getTime();
            if (time == previousTime) return;
            if (time != previousTime + 1) throw new IllegalStateException("Skipped world tick");
            previousTime = time;
            elapsed++;
            if (phase.equals("settling")) {
                if (elapsed == 20) {
                    assertRest(world);
                    phase = "idle";
                    writeMarker("prepared");
                }
                return;
            }
            record(world, "tick");
            if (elapsed == 40) {
                if (!world.getBlockState(PISTON).get(PistonBlock.EXTENDED))
                    throw new IllegalStateException("Fixture did not extend piston");
                toggle(world);
                record(world, "input-off");
                if (!server.getTickManager().step(40)) throw new IllegalStateException("Cannot step second leg");
            }
            if (elapsed == 80) {
                if (world.getBlockState(PISTON).get(PistonBlock.EXTENDED)
                    || !world.getBlockState(new BlockPos(4, 80, 1)).isOf(Blocks.STONE))
                    throw new IllegalStateException("Fixture did not retract mobile block");
                assertRest(world);
                trace.close();
                trace = null;
                phase = "idle";
                writeMarker(run + ".done");
            }
        } catch (Exception e) { fail(e); }
    }

    public static void ready() {
        try { writeMarker("boot-" + System.getProperty("stonebench.boot") + ".ready"); }
        catch (IOException e) { fail(e); }
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

    private static void assertRest(ServerWorld world) {
        JsonObject state = snapshot(world);
        for (String key : List.of("blockTicks", "fluidTicks", "blockEvents"))
            if (!state.getAsJsonArray(key).isEmpty()) throw new IllegalStateException("Pending " + key);
        for (BlockPos pos : BlockPos.iterate(0, 79, 0, 9, 82, 5))
            if (world.getBlockEntity(pos) instanceof PistonBlockEntity)
                throw new IllegalStateException("Moving piston in static checkpoint");
        if (!(world.getBlockEntity(CHEST) instanceof ChestBlockEntity chest)
            || !chest.getStack(0).isOf(Items.DIAMOND) || chest.getStack(0).getCount() != 7)
            throw new IllegalStateException("Inventory fixture missing");
    }

    private static void record(ServerWorld world, String event) throws IOException {
        JsonObject row = new JsonObject(); row.addProperty("tick", elapsed); row.addProperty("event", event);
        row.add("state", snapshot(world)); trace.write(JSON.toJson(row)); trace.newLine(); trace.flush();
    }

    private static void writeMarker(String name) throws IOException {
        Files.createDirectories(OUTPUT); Files.writeString(OUTPUT.resolve(name), "ok\n");
    }

    private static void fail(Exception e) {
        phase = "idle";
        e.printStackTrace();
        try {
            if (trace != null) { trace.close(); trace = null; }
            Files.createDirectories(OUTPUT); Files.writeString(OUTPUT.resolve("error.txt"), e.toString());
        } catch (IOException ignored) { e.printStackTrace(); }
    }
}
