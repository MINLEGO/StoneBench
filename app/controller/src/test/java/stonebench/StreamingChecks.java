package stonebench;

import com.google.gson.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.FileTime;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Bounded-heap checks for large lazy traces, continuity, paging, and artifact integrity. */
public final class StreamingChecks {
    private static final int LARGE_TICKS = 6000;
    private static final int POSITIONS = 512;
    private static final long START_TIME = 1200L;
    private static final long START_INDEX = 900L;

    private StreamingChecks() {}

    public static void main(String[] args) throws IOException {
        Path artifactDirectory = Path.of("stonebench", "artifacts");
        JsonArray blocksForward = blockRows(false, POSITIONS, false);
        JsonArray blocksReverse = blockRows(true, POSITIONS, false);
        check(blocksForward.equals(blocksReverse), "reversed object keys retain semantic equality");
        JsonObject leftBlocks = Artifacts.write("snapshot_blocks", blocksForward.asList());
        JsonObject rightBlocks = Artifacts.write("snapshot_blocks", blocksReverse.asList());
        check(!leftBlocks.get("sha256").getAsString().equals(rightBlocks.get("sha256").getAsString()),
                "row-object key order changes nested artifact bytes and hashes");
        JsonObject leftEvents = Artifacts.write("intratick_events", List.<JsonElement>of());
        JsonObject rightEvents = Artifacts.write("intratick_events", List.<JsonElement>of());

        AtomicInteger leftYielded = new AtomicInteger();
        AtomicInteger rightYielded = new AtomicInteger();
        JsonObject left = writeTrace(LARGE_TICKS, LARGE_TICKS, leftBlocks, leftEvents, 0, 0, null, leftYielded);
        JsonObject right = writeTrace(LARGE_TICKS, LARGE_TICKS, rightBlocks, rightEvents, 0, 0, null, rightYielded);
        check(leftYielded.get() == LARGE_TICKS && rightYielded.get() == LARGE_TICKS,
                "artifact writers consume each lazy trace exactly once");
        check(left.get("count").getAsInt() == LARGE_TICKS && right.get("count").getAsInt() == LARGE_TICKS,
                "large trace references retain their row counts");
        check(!left.get("sha256").getAsString().equals(right.get("sha256").getAsString()),
                "semantically equal trace artifacts may retain distinct serialized hashes");

        long scansBeforeLargeCompare = Artifacts.verificationScans();
        long bytesBeforeLargeCompare = Artifacts.verificationBytes();
        JsonObject equal = compare(left, right);
        long scansForLargeCompare = Artifacts.verificationScans() - scansBeforeLargeCompare;
        long bytesForLargeCompare = Artifacts.verificationBytes() - bytesBeforeLargeCompare;
        check(equal.get("status").getAsString().equals("equal"), "large traces compare semantically equal");
        check(scansForLargeCompare <= 8 && bytesForLargeCompare <= 4_000_000L,
                "cached nested hashes are not re-scanned for every repeated trace row");
        check(equal.getAsJsonObject("left_continuity").get("complete").getAsBoolean()
                        && equal.getAsJsonObject("right_continuity").get("complete").getAsBoolean(),
                "both 6000-tick traces have complete continuity");

        JsonObject smallBlocks = Artifacts.write("snapshot_blocks", blockRows(false, 4, false).asList());
        JsonObject smallEvents = Artifacts.write("intratick_events", List.<JsonElement>of());
        JsonObject smallBaseline = writeTrace(5, 5, smallBlocks, smallEvents, 0, 0, null, new AtomicInteger());
        JsonObject earlyDifference = writeTrace(5, 5, smallBlocks, smallEvents, 2, 0, null, new AtomicInteger());
        JsonObject divergence = compare(earlyDifference, smallBaseline);
        check(divergence.get("status").getAsString().equals("different"), "early difference is reported");
        check(divergence.get("first_tick").getAsInt() == 2, "first differing tick is exact");
        check(divergence.getAsJsonObject("left_continuity").get("complete").getAsBoolean()
                        && divergence.getAsJsonObject("right_continuity").get("complete").getAsBoolean(),
                "the independent right baseline remains complete");
        JsonArray fields = readFields(divergence.getAsJsonObject("first_fields"));
        check(fields.size() == 1 && fields.get(0).getAsJsonObject().get("field").getAsString().equals("$.state.marker"),
                "the early divergence reports only its exact field");
        JsonObject baselineAgain = compare(smallBaseline, writeTrace(5, 5, smallBlocks, smallEvents, 0, 0, null, new AtomicInteger()));
        check(baselineAgain.get("status").getAsString().equals("equal"),
                "comparison leaves the right baseline artifact independently reusable");

        JsonObject leftEpoch = writeTrace(1, 1, smallBlocks, smallEvents, 0, 0, null, new AtomicInteger());
        JsonObject rightEpoch = writeTrace(1, 1, smallBlocks, smallEvents, 0, 0, null, new AtomicInteger(), 4200L, 7000L);
        JsonObject epochDifference = compare(leftEpoch, rightEpoch);
        check(epochDifference.get("status").getAsString().equals("different")
                        && epochDifference.get("first_tick").getAsInt() == 1,
                "an independent baseline with different start clocks diverges on its first tick");
        check(epochDifference.getAsJsonObject("left_continuity").get("complete").getAsBoolean()
                        && epochDifference.getAsJsonObject("right_continuity").get("complete").getAsBoolean(),
                "both independent epoch traces remain continuous");
        JsonArray epochFields = readFields(epochDifference.getAsJsonObject("first_fields"));
        Set<String> epochFieldNames = new HashSet<>();
        for (JsonElement field : epochFields) epochFieldNames.add(field.getAsJsonObject().get("field").getAsString());
        check(epochFieldNames.equals(Set.of("$.simulation_index", "$.world_time")),
                "independent epoch differences expose the exact clock fields");

        JsonObject malformedRight = writeTrace(5, 5, smallBlocks, smallEvents, 0, 5, null, new AtomicInteger());
        JsonObject malformedResult = compare(earlyDifference, malformedRight);
        check(malformedResult.get("status").getAsString().equals("different")
                        && malformedResult.get("first_tick").getAsInt() == 2,
                "an early difference is retained when the later right observation is malformed");
        check(!malformedResult.getAsJsonObject("right_continuity").get("complete").getAsBoolean(),
                "a malformed later right observation invalidates right continuity");

        JsonObject missingRight = writeTrace(4, 5, smallBlocks, smallEvents, 0, 0, null, new AtomicInteger());
        JsonObject missingResult = compare(earlyDifference, missingRight);
        check(missingResult.get("status").getAsString().equals("different")
                        && missingResult.get("first_tick").getAsInt() == 2,
                "an early difference is retained when a later right observation is missing");
        check(!missingResult.getAsJsonObject("right_continuity").get("complete").getAsBoolean(),
                "a missing later right observation invalidates right continuity");

        JsonObject rightLateBlocks = Artifacts.write("snapshot_blocks", blockRows(true, POSITIONS, true).asList());
        JsonObject rightLate = writeTrace(LARGE_TICKS, LARGE_TICKS, rightBlocks, rightEvents, 0, 0,
                rightLateBlocks, new AtomicInteger());
        JsonObject largeEarlyDifference = writeTrace(LARGE_TICKS, LARGE_TICKS, leftBlocks, leftEvents, 2, 0,
                null, new AtomicInteger());
        check(compare(rightLate, rightLate).get("status").getAsString().equals("equal"),
                "the late nested artifact is verified and cached before mutation");
        corruptLastNestedMarker(artifactPath(rightLateBlocks.get("artifact_id").getAsString()));
        boolean corruptTraceRejected = false;
        try {
            compare(largeEarlyDifference, rightLate);
        } catch (IllegalStateException e) {
            corruptTraceRejected = isIntegrityError(e);
        }
        check(corruptTraceRejected,
                "a later nested change after cached reads fails integrity despite an earlier divergence");

        JsonObject paged = paginationAndUnicode(artifactDirectory);
        truncateTraceAndRequireIntegrity(left);
        check(paged.get("count").getAsInt() == 777, "Unicode paging fixture was fully written");
        System.out.println("Streaming checks passed");
    }

    private static JsonArray blockRows(boolean reverse, int count, boolean tailMarker) {
        JsonArray rows = new JsonArray();
        String[] facings = {"north", "south", "east", "west"};
        for (int i = 0; i < count; i++) {
            JsonObject position = new JsonObject();
            position.addProperty("x", 1024 + i);
            position.addProperty("y", 64 + i % 48);
            position.addProperty("z", 1024 + i / 32);

            JsonObject properties = new JsonObject();
            properties.addProperty("facing", facings[i % facings.length]);
            properties.addProperty("type", "single");
            JsonObject state = new JsonObject();
            state.addProperty("block", "minecraft:chest");
            state.add("parameters", properties);

            JsonObject item = new JsonObject();
            item.addProperty("slot", 0);
            item.addProperty("item", "minecraft:iron_ingot");
            item.addProperty("count", 64);
            JsonArray inventory = new JsonArray();
            inventory.add(item);

            JsonObject record = new JsonObject();
            if (reverse) {
                record.add("inventory", inventory);
                record.add("state", state);
                record.add("position", position);
            } else {
                record.add("position", position);
                record.add("state", state);
                record.add("inventory", inventory);
            }
            if (tailMarker && i == count - 1) record.addProperty("tail_marker", "stable");
            rows.add(record);
        }
        return rows;
    }

    private static JsonObject writeTrace(int rowCount, int expectedTicks, JsonObject blocks, JsonObject events,
                                        int divergenceTick, int malformedTick, JsonObject finalBlocks,
                                        AtomicInteger yielded) {
        return writeTrace(rowCount, expectedTicks, blocks, events, divergenceTick, malformedTick, finalBlocks,
                yielded, START_TIME, START_INDEX);
    }

    private static JsonObject writeTrace(int rowCount, int expectedTicks, JsonObject blocks, JsonObject events,
                                         int divergenceTick, int malformedTick, JsonObject finalBlocks,
                                         AtomicInteger yielded, long startTime, long startIndex) {
        JsonObject metadata = new JsonObject();
        metadata.addProperty("expected_ticks", expectedTicks);
        metadata.addProperty("start_world_time", startTime);
        metadata.addProperty("start_simulation_index", startIndex);
        return Artifacts.write("trace", new TraceRows(rowCount, blocks, events, divergenceTick, malformedTick,
                finalBlocks, yielded, startTime, startIndex), metadata);
    }

    private static JsonObject compare(JsonObject left, JsonObject right) {
        JsonObject args = new JsonObject();
        args.addProperty("left", left.get("artifact_id").getAsString());
        args.addProperty("right", right.get("artifact_id").getAsString());
        return Observation.compareTraces(args).getAsJsonObject("comparison");
    }

    private static JsonArray readFields(JsonObject reference) {
        check(reference.get("kind").getAsString().equals("divergent_fields"), "first fields are an artifact reference");
        JsonObject args = new JsonObject();
        args.addProperty("artifact_id", reference.get("artifact_id").getAsString());
        args.addProperty("offset", 0);
        args.addProperty("limit", 256);
        return Artifacts.read(args).getAsJsonArray("entries");
    }

    private static JsonObject paginationAndUnicode(Path artifactDirectory) {
        List<JsonElement> rows = new ArrayList<>(777);
        for (int i = 0; i < 777; i++) {
            JsonObject row = new JsonObject();
            row.addProperty("index", i);
            row.addProperty("label", "雪と石・" + i + " 🪨");
            rows.add(row);
        }
        JsonObject reference = Artifacts.write("unicode_pages", rows);
        for (int i = 0; i < 65; i++) {
            JsonObject evictionRow = new JsonObject();
            evictionRow.addProperty("sequence", i);
            Artifacts.write("cache_eviction", List.of(evictionRow));
        }
        long scansBeforePages = Artifacts.verificationScans();
        long bytesBeforePages = Artifacts.verificationBytes();
        int[] offsets = {0, 1, 255, 256, 257, 511, 768};
        for (int offset : offsets) {
            JsonObject args = new JsonObject();
            args.addProperty("artifact_id", reference.get("artifact_id").getAsString());
            args.addProperty("offset", offset);
            args.addProperty("limit", 256);
            JsonObject page = Artifacts.read(args);
            JsonArray entries = page.getAsJsonArray("entries");
            int expectedSize = Math.min(256, 777 - offset);
            check(entries.size() == expectedSize, "page at offset " + offset + " has the requested bounded size");
            JsonObject first = entries.get(0).getAsJsonObject();
            check(first.get("index").getAsInt() == offset, "seek returns the requested row at " + offset);
            check(first.get("label").getAsString().equals("雪と石・" + offset + " 🪨"), "UTF-8 round-trips at offset " + offset);
            int nextOffset = offset + entries.size();
            check(page.get("next_offset").isJsonNull() == (nextOffset == 777), "page completion matches its end offset");
            if (nextOffset < 777) check(page.get("next_offset").getAsInt() == nextOffset, "next page offset is exact");
        }
        check(Artifacts.verificationScans() - scansBeforePages == 1,
                "the first page hashes the evicted Unicode artifact exactly once");
        check(Artifacts.verificationBytes() - bytesBeforePages == reference.get("bytes").getAsLong(),
                "sparse Unicode seeks reuse the verified byte index");
        check(artifactDirectory.toFile().isDirectory(), "isolated artifact directory was created");
        return reference;
    }

    private static void corruptLastNestedMarker(Path path) throws IOException {
        try (RandomAccessFile file = new RandomAccessFile(path.toFile(), "rw")) {
            long end = file.length();
            if (end > 0) {
                file.seek(end - 1);
                if (file.readByte() == '\n') end--;
            }
            long start = end;
            while (start > 0) {
                file.seek(start - 1);
                if (file.readByte() == '\n') break;
                start--;
            }
            int lineLength = Math.toIntExact(end - start);
            byte[] line = new byte[lineLength];
            file.seek(start);
            file.readFully(line);
            String text = new String(line, StandardCharsets.UTF_8);
            String marker = "\"tail_marker\":\"stable\"";
            int markerStart = text.indexOf(marker);
            check(markerStart >= 0, "final trace row has its nested-corruption marker");
            long valueStart = start + markerStart + marker.indexOf("stable");
            file.seek(valueStart);
            file.write("alterd".getBytes(StandardCharsets.UTF_8));
        }
        FileTime modified = Files.getLastModifiedTime(path);
        Files.setLastModifiedTime(path, FileTime.fromMillis(modified.toMillis() + 2000));
    }

    private static void truncateTraceAndRequireIntegrity(JsonObject reference) throws IOException {
        Path path = artifactPath(reference.get("artifact_id").getAsString());
        long originalSize = Files.size(path);
        check(originalSize > 1, "trace artifact has bytes to truncate");
        try (var channel = Files.newByteChannel(path, StandardOpenOption.WRITE)) {
            channel.truncate(originalSize - 1);
        }
        boolean rejected = false;
        try {
            JsonObject args = new JsonObject();
            args.addProperty("artifact_id", reference.get("artifact_id").getAsString());
            args.addProperty("offset", 0);
            args.addProperty("limit", 1);
            Artifacts.read(args);
        } catch (IllegalStateException e) {
            rejected = isIntegrityError(e);
        }
        check(rejected, "truncated trace page fails its cached integrity check");
    }

    private static Path artifactPath(String id) {
        return Path.of("stonebench", "artifacts", id + ".jsonl");
    }

    private static boolean isIntegrityError(IllegalStateException error) {
        String message = error.getMessage() == null ? "" : error.getMessage().toLowerCase(Locale.ROOT);
        return message.contains("integrity") || message.contains("hash") || message.contains("truncat");
    }

    private static final class TraceRows implements Iterable<JsonElement> {
        private final int rowCount;
        private final JsonObject blocks;
        private final JsonObject events;
        private final int divergenceTick;
        private final int malformedTick;
        private final JsonObject finalBlocks;
        private final AtomicInteger yielded;
        private final long startTime;
        private final long startIndex;

        private TraceRows(int rowCount, JsonObject blocks, JsonObject events, int divergenceTick,
                          int malformedTick, JsonObject finalBlocks, AtomicInteger yielded,
                          long startTime, long startIndex) {
            this.rowCount = rowCount;
            this.blocks = blocks;
            this.events = events;
            this.divergenceTick = divergenceTick;
            this.malformedTick = malformedTick;
            this.finalBlocks = finalBlocks;
            this.yielded = yielded;
            this.startTime = startTime;
            this.startIndex = startIndex;
        }

        @Override
        public Iterator<JsonElement> iterator() {
            return new Iterator<>() {
                private int tick;

                @Override
                public boolean hasNext() {
                    return tick < rowCount;
                }

                @Override
                public JsonElement next() {
                    if (!hasNext()) throw new NoSuchElementException();
                    int currentTick = ++tick;
                    JsonObject state = new JsonObject();
                    state.add("blocks", currentTick == rowCount && finalBlocks != null ? finalBlocks : blocks);
                    state.add("block_ticks", new JsonArray());
                    state.add("fluid_ticks", new JsonArray());
                    state.add("block_events", new JsonArray());
                    JsonObject coverage = new JsonObject();
                    coverage.addProperty("status", "covered");
                    coverage.addProperty("certification", false);
                    state.add("coverage", coverage);
                    state.addProperty("marker", currentTick == divergenceTick ? "different" : "baseline");
                    if (currentTick == malformedTick) state.remove("coverage");

                    JsonObject observation = new JsonObject();
                    observation.addProperty("tick_index", currentTick);
                    observation.addProperty("simulation_index", startIndex + currentTick);
                    observation.addProperty("world_time", startTime + currentTick);
                    observation.addProperty("phase", "end_tick");
                    observation.addProperty("complete", true);
                    observation.add("state", state);
                    observation.add("events", events);
                    if (currentTick == rowCount) observation.addProperty("tail_marker", "stable");
                    yielded.incrementAndGet();
                    return observation;
                }
            };
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
