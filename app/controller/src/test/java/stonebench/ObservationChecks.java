package stonebench;

import com.google.gson.*;
import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import net.minecraft.nbt.*;

public final class ObservationChecks {
    private ObservationChecks() {}

    public static void main(String[] args) throws IOException {
        typedNbt();
        comparisonKeepsInventoryAndTime();
        continuityRequiresEveryTick();
        firstDivergenceReportsTickAndFields();
        artifactsArePagedAndIntegrityChecked();
        System.out.println("Observation checks passed");
    }

    private static void typedNbt() {
        JsonObject byteValue = TypedNbt.encode(NbtByte.of((byte) 7));
        JsonObject intValue = TypedNbt.encode(NbtInt.of(7));
        JsonObject longValue = TypedNbt.encode(NbtLong.of(9007199254740993L));
        check(byteValue.get("type").getAsInt() == 1 && byteValue.get("value").getAsString().equals("7b"), "byte keeps its NBT type");
        check(intValue.get("type").getAsInt() == 3 && intValue.get("value").getAsString().equals("7"), "int keeps its NBT type");
        check(!byteValue.equals(intValue), "byte and int remain distinguishable");
        check(longValue.get("type").getAsInt() == 4
                && longValue.get("value").getAsString().equals("9007199254740993L"), "large long stays exact beyond 2^53");

        JsonObject floatValue = TypedNbt.encode(NbtFloat.of(1.5f));
        JsonObject doubleValue = TypedNbt.encode(NbtDouble.of(1.5d));
        check(floatValue.get("type").getAsInt() == 5 && floatValue.get("value").getAsString().equals("1.5f"), "float suffix and type remain visible");
        check(doubleValue.get("type").getAsInt() == 6 && doubleValue.get("value").getAsString().equals("1.5d"), "double suffix and type remain visible");
        check(!floatValue.equals(doubleValue), "float and double remain distinguishable");

        NbtCompound compound = new NbtCompound();
        compound.put("z", NbtInt.of(1));
        compound.put("a", NbtByte.of((byte) 2));
        JsonObject encodedCompound = TypedNbt.encode(compound);
        List<String> keys = new ArrayList<>(encodedCompound.getAsJsonObject("value").keySet());
        check(keys.equals(List.of("a", "z")), "compound keys are sorted");

        NbtList list = new NbtList();
        list.add(NbtInt.of(2));
        list.add(NbtInt.of(1));
        JsonArray encodedValues = TypedNbt.encode(list).getAsJsonArray("value");
        check(encodedValues.size() == 2
                && encodedValues.get(0).getAsJsonObject().get("type").getAsInt() == 3
                && encodedValues.get(0).getAsJsonObject().get("value").getAsString().equals("2")
                && encodedValues.get(1).getAsJsonObject().get("type").getAsInt() == 3
                && encodedValues.get(1).getAsJsonObject().get("value").getAsString().equals("1"),
                "list element order and types are preserved");

        NbtList compoundList = new NbtList();
        NbtCompound first = new NbtCompound();
        first.put("value", NbtByte.of((byte) 3));
        NbtCompound second = new NbtCompound();
        second.put("value", NbtLong.of(4L));
        compoundList.add(first);
        compoundList.add(second);
        JsonArray encodedCompounds = TypedNbt.encode(compoundList).getAsJsonArray("value");
        check(encodedCompounds.get(0).getAsJsonObject().getAsJsonObject("value").get("value").getAsJsonObject().get("type").getAsInt() == 1
                && encodedCompounds.get(1).getAsJsonObject().getAsJsonObject("value").get("value").getAsJsonObject().get("type").getAsInt() == 4,
                "list order retains each compound's nested numeric type");

        JsonObject emptyList = TypedNbt.encode(new NbtList());
        check(emptyList.get("type").getAsInt() == 9 && emptyList.getAsJsonArray("value").size() == 0,
                "empty list retains its list tag and empty value");
    }

    private static void comparisonKeepsInventoryAndTime() {
        JsonObject before = new JsonObject();
        JsonArray beforeInventory = new JsonArray();
        JsonObject beforeItem = new JsonObject();
        beforeItem.addProperty("count", 1);
        beforeInventory.add(beforeItem);
        before.add("inventory", beforeInventory);
        before.addProperty("world_time", 100L);
        before.addProperty("simulation_index", 20L);

        JsonObject after = new JsonObject();
        JsonArray afterInventory = new JsonArray();
        JsonObject afterItem = new JsonObject();
        afterItem.addProperty("count", 2);
        afterInventory.add(afterItem);
        after.add("inventory", afterInventory);
        after.addProperty("world_time", 101L);
        after.addProperty("simulation_index", 21L);

        Set<String> fields = fieldNames(ObservationComparison.fields(before, after));
        check(fields.contains("$.inventory[0].count"), "inventory changes are compared");
        check(fields.contains("$.world_time") && fields.contains("$.simulation_index"), "temporal changes are compared");
    }

    private static void continuityRequiresEveryTick() {
        long startTime = 100L;
        long startIndex = 50L;
        List<JsonObject> four = observations(4, startTime, startIndex);
        check(ObservationComparison.continuity(four, 4, startTime, startIndex).get("complete").getAsBoolean(),
                "exact complete trace is continuous");

        check(!ObservationComparison.continuity(new ArrayList<>(four.subList(1, 4)), 4, startTime, startIndex)
                .get("complete").getAsBoolean(), "missing first tick is detected");
        List<JsonObject> missingInternal = new ArrayList<>(four);
        missingInternal.remove(1);
        check(!ObservationComparison.continuity(missingInternal, 4, startTime, startIndex)
                .get("complete").getAsBoolean(), "missing internal tick is detected");
        check(!ObservationComparison.continuity(new ArrayList<>(four.subList(0, 3)), 4, startTime, startIndex)
                .get("complete").getAsBoolean(), "missing last tick is detected");

        List<JsonObject> falseComplete = new ArrayList<>(four);
        falseComplete.set(2, four.get(2).deepCopy());
        falseComplete.get(2).addProperty("complete", false);
        check(!ObservationComparison.continuity(falseComplete, 4, startTime, startIndex)
                .get("complete").getAsBoolean(), "false complete flag is detected");

        List<JsonObject> missingState = new ArrayList<>(four);
        missingState.set(1, four.get(1).deepCopy());
        missingState.get(1).remove("state");
        check(!ObservationComparison.continuity(missingState, 4, startTime, startIndex)
                .get("complete").getAsBoolean(), "missing complete state is detected");

        List<JsonObject> missingBlockQueue = new ArrayList<>(four);
        missingBlockQueue.set(1, four.get(1).deepCopy());
        missingBlockQueue.get(1).getAsJsonObject("state").remove("block_ticks");
        check(!ObservationComparison.continuity(missingBlockQueue, 4, startTime, startIndex)
                .get("complete").getAsBoolean(), "missing block tick queue is detected");

        List<JsonObject> missingEvents = new ArrayList<>(four);
        missingEvents.set(1, four.get(1).deepCopy());
        missingEvents.get(1).remove("events");
        check(!ObservationComparison.continuity(missingEvents, 4, startTime, startIndex)
                .get("complete").getAsBoolean(), "missing events is detected");
    }

    private static void firstDivergenceReportsTickAndFields() {
        long startTime = 200L;
        long startIndex = 80L;
        List<JsonObject> left = observations(3, startTime, startIndex);
        List<JsonObject> right = observations(3, startTime, startIndex);
        right.get(1).getAsJsonObject("state").addProperty("inventory_count", 1);

        JsonObject result = ObservationComparison.firstDivergence(left, right, 3, startTime, startIndex);
        check(result.get("status").getAsString().equals("different"), "divergent traces report different");
        check(result.get("first_tick").getAsInt() == 2, "first divergent tick is reported");
        JsonArray fields = result.getAsJsonArray("first_fields");
        check(fields.size() == 1
                && fields.get(0).getAsJsonObject().get("field").getAsString().equals("$.state.inventory_count"),
                "first divergence includes changed field paths");
    }

    private static void artifactsArePagedAndIntegrityChecked() throws IOException {
        List<JsonObject> rows = List.of(artifactRow(1), artifactRow(2), artifactRow(3));
        JsonObject written = Artifacts.write("observation_checks", rows);
        String id = written.get("artifact_id").getAsString();
        check(written.get("count").getAsInt() == 3 && written.get("complete").getAsBoolean(),
                "artifact reference reports its row count and completion");
        check(written.get("sha256").getAsString().matches("[0-9a-f]{64}"), "artifact reference carries SHA-256");

        written.addProperty("count", 99);
        check(Artifacts.reference(id).get("count").getAsInt() == 3, "returned artifact references are immutable copies");

        JsonObject firstPage = Artifacts.read(pageArgs(id, 0, 2));
        check(firstPage.getAsJsonArray("entries").size() == 2
                && firstPage.get("next_offset").getAsInt() == 2
                && !firstPage.get("complete").getAsBoolean()
                && firstPage.getAsJsonObject("artifact").get("count").getAsInt() == 3,
                "first page reports entries, total count, and continuation");
        JsonObject lastPage = Artifacts.read(pageArgs(id, 2, 2));
        check(lastPage.getAsJsonArray("entries").size() == 1
                && lastPage.get("next_offset").isJsonNull()
                && lastPage.get("complete").getAsBoolean(), "last page reports completion");
        List<JsonObject> all = Artifacts.all(id);
        check(all.size() == rows.size() && all.equals(rows), "all reads every stored page in order");

        Path artifact = Path.of("stonebench", "artifacts", id + ".jsonl");
        byte[] bytes = Files.readAllBytes(artifact);
        check(bytes.length > 1, "artifact has bytes to truncate");
        Files.write(artifact, Arrays.copyOf(bytes, bytes.length - 1));
        boolean rejected = false;
        try {
            Artifacts.read(pageArgs(id, 0, 1));
        } catch (IllegalStateException e) {
            rejected = e.getMessage().contains("integrity");
        }
        check(rejected, "truncated artifact fails its integrity hash");
    }

    private static JsonObject pageArgs(String id, int offset, int limit) {
        JsonObject args = new JsonObject();
        args.addProperty("artifact_id", id);
        args.addProperty("offset", offset);
        args.addProperty("limit", limit);
        return args;
    }

    private static JsonObject artifactRow(int index) {
        JsonObject row = new JsonObject();
        row.addProperty("index", index);
        row.addProperty("label", "row-" + index);
        return row;
    }

    private static List<JsonObject> observations(int count, long startTime, long startIndex) {
        List<JsonObject> rows = new ArrayList<>();
        for (int tick = 1; tick <= count; tick++) {
            JsonObject row = new JsonObject();
            row.addProperty("tick_index", tick);
            row.addProperty("simulation_index", startIndex + tick);
            row.addProperty("world_time", startTime + tick);
            row.addProperty("phase", "end_tick");
            row.addProperty("complete", true);
            JsonObject state = new JsonObject();
            state.addProperty("inventory_count", 0);
            state.add("blocks", new JsonArray());
            state.add("block_ticks", new JsonArray());
            state.add("fluid_ticks", new JsonArray());
            state.add("block_events", new JsonArray());
            state.add("coverage", new JsonObject());
            row.add("state", state);
            row.add("events", new JsonArray());
            rows.add(row);
        }
        return rows;
    }

    private static Set<String> fieldNames(JsonArray rows) {
        Set<String> names = new HashSet<>();
        for (JsonElement row : rows) names.add(row.getAsJsonObject().get("field").getAsString());
        return names;
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
