package stonebench;

import com.google.gson.*;
import java.util.*;

/** Compares trace rows and their referenced row artifacts without loading either history into memory. */
final class TraceComparison {
    private TraceComparison() {}

    static JsonObject compare(String leftId, String rightId) {
        JsonObject leftRef = Artifacts.reference(leftId);
        JsonObject rightRef = Artifacts.reference(rightId);
        requireKind(leftRef, "trace");
        requireKind(rightRef, "trace");
        ObservationComparison.ContinuityTracker leftContinuity = continuity(leftRef);
        ObservationComparison.ContinuityTracker rightContinuity = continuity(rightRef);
        JsonObject firstFields = null;
        int firstTick = 0;
        int position = 0;

        try (Artifacts.Cursor left = Artifacts.open(leftId); Artifacts.Cursor right = Artifacts.open(rightId)) {
            while (true) {
                JsonObject before = left.next();
                JsonObject after = right.next();
                if (before == null && after == null) break;
                position++;
                if (before != null) leftContinuity.accept(before);
                if (after != null) rightContinuity.accept(after);

                if (firstFields == null) {
                    if (mayDiffer(before, after)) {
                        JsonObject fields = writeFields(before, after);
                        if (fields != null) {
                            firstFields = fields;
                            firstTick = position;
                        }
                    }
                } else {
                    compareNested(before, after, null);
                }
            }
        }

        JsonObject leftResult = leftContinuity.finish();
        JsonObject rightResult = rightContinuity.finish();
        boolean complete = leftResult.get("complete").getAsBoolean() && rightResult.get("complete").getAsBoolean();
        JsonObject result = new JsonObject();
        result.add("left_continuity", leftResult);
        result.add("right_continuity", rightResult);
        if (firstFields != null) {
            result.addProperty("status", "different");
            result.addProperty("first_tick", firstTick);
            result.add("first_fields", firstFields);
        } else {
            result.addProperty("status", complete ? "equal" : "incomplete");
        }
        return result;
    }

    private static ObservationComparison.ContinuityTracker continuity(JsonObject ref) {
        return ObservationComparison.continuityTracker(
            integer(ref, "expected_ticks"), number(ref, "start_world_time"), number(ref, "start_simulation_index"));
    }

    private static int integer(JsonObject object, String key) {
        long value = number(object, key);
        if (value > Integer.MAX_VALUE) throw new IllegalStateException("Invalid trace " + key);
        return (int) value;
    }

    private static long number(JsonObject object, String key) {
        try {
            JsonElement value = object.get(key);
            if (value == null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isNumber()) throw new NumberFormatException();
            return new java.math.BigDecimal(value.getAsString()).longValueExact();
        } catch (RuntimeException e) {
            throw new IllegalStateException("Invalid trace " + key, e);
        }
    }

    private static void requireKind(JsonObject ref, String kind) {
        if (!kind.equals(ref.get("kind").getAsString())) throw new IllegalArgumentException("compare_traces requires trace artifacts");
    }

    /** Avoids creating a difference artifact for equal rows with matching verified nested hashes. */
    private static boolean mayDiffer(JsonObject before, JsonObject after) {
        if (before == null || after == null) return before != after;
        if (!ObservationComparison.same(withoutNestedRows(before), withoutNestedRows(after))) return true;
        for (NestedPair pair : nestedPairs(before, after)) {
            if (sameNested(pair.before, pair.after)) continue;
            return true;
        }
        return false;
    }

    private static JsonObject writeFields(JsonObject before, JsonObject after) {
        try (LazyFields writer = new LazyFields()) {
            JsonElement beforeMetadata = before == null ? null : withoutNestedRows(before);
            JsonElement afterMetadata = after == null ? null : withoutNestedRows(after);
            ObservationComparison.fieldsAt("$", beforeMetadata, afterMetadata, writer);
            compareNested(before, after, writer);
            return writer.finish();
        }
    }

    /** Validates and consumes every nested reference, even after the first divergent tick. */
    private static void compareNested(JsonObject before, JsonObject after, java.util.function.Consumer<JsonObject> emit) {
        for (NestedPair pair : nestedPairs(before, after)) compareNested(pair.before, pair.after, emit);
    }

    /** Opens the difference artifact only after the first field actually differs. */
    private static final class LazyFields implements java.util.function.Consumer<JsonObject>, AutoCloseable {
        private Artifacts.Writer writer;
        JsonObject finish() {
            if (writer == null) return null;
            JsonObject result = writer.finish();
            writer = null;
            return result;
        }
        @Override public void accept(JsonObject row) {
            if (writer == null) writer = Artifacts.writer("divergent_fields");
            writer.add(row);
        }
        @Override public void close() {
            if (writer != null) {
                writer.close();
                writer = null;
            }
        }
    }

    private static boolean sameNested(Nested before, Nested after) {
        if (before.artifact != null && after.artifact != null) {
            JsonObject a = before.artifact.descriptor;
            JsonObject b = after.artifact.descriptor;
            boolean same = a.get("count").equals(b.get("count"))
                && a.get("bytes").equals(b.get("bytes"))
                && a.get("sha256").equals(b.get("sha256"));
            if (same) {
                Artifacts.verify(before.artifact.id);
                if (!before.artifact.id.equals(after.artifact.id)) Artifacts.verify(after.artifact.id);
                return true;
            }
            return false;
        }
        if (isRows(before) && isRows(after)) return ObservationComparison.same(before.raw, after.raw);
        return !isRows(before) && !isRows(after) && ObservationComparison.same(before.raw, after.raw);
    }

    private static void compareNested(Nested before, Nested after, java.util.function.Consumer<JsonObject> emit) {
        if (emit == null) {
            if (before.artifact != null) Artifacts.verify(before.artifact.id);
            if (after.artifact != null) Artifacts.verify(after.artifact.id);
            return;
        }
        if (before.artifact != null && after.artifact != null && sameArtifactContent(before.artifact, after.artifact)) {
            verifyPair(before.artifact, after.artifact);
            return;
        }
        boolean beforeRows = isRows(before);
        boolean afterRows = isRows(after);
        if (beforeRows && afterRows) {
            boolean differs = false;
            try (Rows a = rows(before); Rows b = rows(after)) {
                int index = 0;
                while (true) {
                    JsonElement left = a.next();
                    JsonElement right = b.next();
                    if (left == null && right == null) break;
                    if (!Objects.equals(left, right)) {
                        differs = true;
                        if (emit != null) ObservationComparison.fieldsAt(before.path + "[" + index + "]", left, right, emit);
                    }
                    index++;
                }
            }
            return;
        }
        if (before.artifact != null) Artifacts.verify(before.artifact.id);
        if (after.artifact != null) Artifacts.verify(after.artifact.id);
        if (!beforeRows && !afterRows) ObservationComparison.fieldsAt(before.path, before.raw, after.raw, emit);
    }

    private static boolean sameArtifactContent(ArtifactReference before, ArtifactReference after) {
        JsonObject a = before.descriptor;
        JsonObject b = after.descriptor;
        return a.get("count").equals(b.get("count"))
            && a.get("bytes").equals(b.get("bytes"))
            && a.get("sha256").equals(b.get("sha256"));
    }

    private static void verifyPair(ArtifactReference before, ArtifactReference after) {
        Artifacts.verify(before.id);
        if (!before.id.equals(after.id)) Artifacts.verify(after.id);
    }

    private static Rows rows(Nested nested) {
        if (nested.artifact != null) {
            Artifacts.Cursor cursor = Artifacts.open(nested.artifact.id);
            return new Rows() {
                @Override public JsonElement next() { return cursor.next(); }
                @Override public void close() { cursor.close(); }
            };
        }
        if (nested.emptyRows || nested.raw == null) return new Rows() {
            @Override public JsonElement next() { return null; }
            @Override public void close() {}
        };
        JsonArray array = nested.raw.getAsJsonArray();
        return new Rows() {
            private int index;
            @Override public JsonElement next() { return index < array.size() ? array.get(index++) : null; }
            @Override public void close() {}
        };
    }

    private static boolean isRows(JsonElement value) {
        if (value == null) return false;
        if (value.isJsonArray()) return true;
        return value.isJsonObject() && value.getAsJsonObject().has("artifact_id");
    }

    private static boolean isRows(Nested nested) {
        return nested.emptyRows || isRows(nested.raw);
    }

    private static List<NestedPair> nestedPairs(JsonObject before, JsonObject after) {
        return List.of(
            new NestedPair(nested(before, after, "$.state.blocks", "snapshot_blocks"), nested(after, before, "$.state.blocks", "snapshot_blocks")),
            new NestedPair(nested(before, after, "$.events", "intratick_events"), nested(after, before, "$.events", "intratick_events")),
            new NestedPair(nested(before, after, "$.adapter_blocks", "input_adapter_blocks"), nested(after, before, "$.adapter_blocks", "input_adapter_blocks")),
            new NestedPair(nested(before, after, "$.construction_blocks", "input_construction_blocks"), nested(after, before, "$.construction_blocks", "input_construction_blocks"))
        );
    }

    private static Nested nested(JsonObject tick, JsonObject other, String path, String expectedKind) {
        JsonElement raw = null;
        if (tick != null) {
            if (!path.equals("$.state.blocks")) raw = tick.get(path.substring(2));
            else if (tick.has("state") && tick.get("state").isJsonObject()) raw = tick.getAsJsonObject("state").get("blocks");
        }
        ArtifactReference artifact = artifact(raw, expectedKind);
        // A missing sequence is empty for row traversal; its missing property remains visible in tick metadata.
        if (raw == null && other != null) {
            JsonElement otherRaw = !path.equals("$.state.blocks") ? other.get(path.substring(2))
                : other.has("state") && other.get("state").isJsonObject() ? other.getAsJsonObject("state").get("blocks") : null;
            if (isRows(otherRaw)) return new Nested(path, null, null, true);
        }
        return new Nested(path, raw, artifact, false);
    }

    private static ArtifactReference artifact(JsonElement raw, String expectedKind) {
        if (raw == null || !raw.isJsonObject() || !raw.getAsJsonObject().has("artifact_id")) return null;
        JsonObject pointer = raw.getAsJsonObject();
        JsonElement idValue = pointer.get("artifact_id");
        if (idValue == null || !idValue.isJsonPrimitive() || !idValue.getAsJsonPrimitive().isString()) {
            throw new IllegalStateException("Invalid nested artifact reference");
        }
        String id = idValue.getAsString();
        JsonObject descriptor = Artifacts.reference(id);
        requireKind(descriptor, expectedKind);
        for (String key : List.of("artifact_id", "kind", "count", "sha256", "bytes", "complete")) {
            if (!pointer.has(key) || !pointer.get(key).equals(descriptor.get(key))) {
                throw new IllegalStateException("Nested artifact reference descriptor mismatch: " + id);
            }
        }
        return new ArtifactReference(id, descriptor);
    }

    private static JsonObject withoutNestedRows(JsonObject tick) {
        JsonObject result = new JsonObject();
        for (var entry : tick.entrySet()) {
            if (Set.of("events","adapter_blocks","construction_blocks").contains(entry.getKey())) {
                result.add(entry.getKey(), rowsMarker(entry.getValue()));
            } else if (entry.getKey().equals("state") && entry.getValue().isJsonObject()) {
                JsonObject state = new JsonObject();
                for (var value : entry.getValue().getAsJsonObject().entrySet()) {
                    if (value.getKey().equals("blocks")) state.add("blocks", rowsMarker(value.getValue()));
                    else state.add(value.getKey(), value.getValue());
                }
                result.add("state", state);
            } else {
                result.add(entry.getKey(), entry.getValue());
            }
        }
        return result;
    }

    private static JsonElement rowsMarker(JsonElement value) {
        return isRows(value) ? new JsonArray() : value;
    }

    private interface Rows extends AutoCloseable {
        JsonElement next();
        @Override void close();
    }

    private record ArtifactReference(String id, JsonObject descriptor) {}
    private record Nested(String path, JsonElement raw, ArtifactReference artifact, boolean emptyRows) {}
    private record NestedPair(Nested before, Nested after) {}
}
