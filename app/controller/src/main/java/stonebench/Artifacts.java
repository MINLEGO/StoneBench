package stonebench;

import com.google.gson.*;
import java.io.*;
import java.nio.channels.Channels;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.FileTime;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.*;

/** Immutable JSONL artifacts. Pages carry counts and an integrity hash, never an implicit limit. */
final class Artifacts {
    private static final Gson JSON = new GsonBuilder().serializeNulls().disableHtmlEscaping().create();
    private static final int PAGE_SIZE = 256;
    private static final int VERIFY_CACHE_SIZE = 64;
    private static final Set<String> RESERVED = Set.of("artifact_id", "kind", "count", "sha256", "bytes", "complete");
    private static final LinkedHashMap<String, CachedReference> REFERENCES = new LinkedHashMap<>(16, .75f, true);
    private static final LinkedHashMap<String, Verification> VERIFIED = new LinkedHashMap<>(16, .75f, true);
    private static long verificationScans;
    private static long verificationBytes;

    private Artifacts() {}

    static JsonObject write(String kind, Collection<? extends JsonElement> rows) {
        return write(kind, (Iterable<? extends JsonElement>) rows, new JsonObject());
    }

    static JsonObject write(String kind, Collection<? extends JsonElement> rows, JsonObject metadata) {
        return write(kind, (Iterable<? extends JsonElement>) rows, metadata);
    }

    static JsonObject write(String kind, Iterable<? extends JsonElement> rows) {
        return write(kind, rows, new JsonObject());
    }

    /** Writes rows as they are produced; the source iterable is never materialized. */
    static JsonObject write(String kind, Iterable<? extends JsonElement> rows, JsonObject metadata) {
        try (Writer writer = writer(kind, metadata)) {
            for (JsonElement row : rows) writer.add(row);
            return writer.finish();
        }
    }

    static Writer writer(String kind) {
        return writer(kind, new JsonObject());
    }

    static Writer writer(String kind, JsonObject metadata) {
        try {
            return new Writer(kind, metadata);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    static JsonObject read(JsonObject args) {
        String id = Task.string(args, "artifact_id");
        JsonObject ref = reference(id);
        int count = count(ref);
        int offset = Task.integer(args, "offset", 0, count);
        int limit = Task.integer(args, "limit", 1, PAGE_SIZE);
        Path file = path(id);
        Verification verification = verify(id, file, ref);
        JsonArray entries = new JsonArray();
        int expected = Math.min(limit, count - offset);
        try {
            if (expected > 0) {
                int baseRow = offset / PAGE_SIZE * PAGE_SIZE;
                long startByte = verification.offsets.get(baseRow / PAGE_SIZE);
                try (FileChannel channel = FileChannel.open(file, StandardOpenOption.READ)) {
                    channel.position(startByte);
                    try (BufferedReader lines = new BufferedReader(new InputStreamReader(Channels.newInputStream(channel), StandardCharsets.UTF_8))) {
                        int skip = offset - baseRow;
                        for (int i = 0; i < skip; i++) {
                            if (lines.readLine() == null) throw rowCountFailure(id);
                        }
                        for (int i = 0; i < expected; i++) {
                            String line = lines.readLine();
                            if (line == null) throw rowCountFailure(id);
                            entries.add(parseRow(line, id));
                        }
                    }
                }
            }
            ensureFingerprint(file, verification.fingerprint, id);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        if (entries.size() != expected) throw rowCountFailure(id);
        JsonObject result = new JsonObject();
        result.add("artifact", ref.deepCopy());
        result.add("entries", entries);
        result.addProperty("offset", offset);
        int next = offset + entries.size();
        result.add("next_offset", next < count ? new JsonPrimitive(next) : JsonNull.INSTANCE);
        result.addProperty("complete", next == count);
        return result;
    }

    static JsonObject reference(String id) {
        requireUuid(id);
        Path metadata = Path.of(path(id) + ".meta");
        Fingerprint before = fingerprint(metadata, id + " metadata");
        synchronized (Artifacts.class) {
            CachedReference cached = REFERENCES.get(id);
            if (cached != null && cached.fingerprint.equals(before)) {
                validateReference(cached.ref, id);
                return cached.ref.deepCopy();
            }
        }
        final JsonObject ref;
        try {
            JsonElement parsed = JsonParser.parseString(Files.readString(metadata, StandardCharsets.UTF_8));
            if (!parsed.isJsonObject()) throw new IllegalStateException("Invalid artifact reference: " + id);
            ref = parsed.getAsJsonObject();
        } catch (IOException | JsonParseException e) {
            throw new IllegalArgumentException("Unknown or invalid artifact in this attempt: " + id, e);
        }
        validateReference(ref, id);
        Fingerprint after = fingerprint(metadata, id + " metadata");
        if (!before.equals(after)) throw new IllegalStateException("Artifact reference changed while reading: " + id);
        synchronized (Artifacts.class) {
            REFERENCES.put(id, new CachedReference(ref.deepCopy(), after));
            trim(REFERENCES, VERIFY_CACHE_SIZE);
        }
        return ref.deepCopy();
    }

    /** Verifies an artifact without parsing its rows; used when equal hashes allow comparison to skip them. */
    static void verify(String id) {
        JsonObject ref = reference(id);
        verify(id, path(id), ref);
    }

    static synchronized long verificationScans() { return verificationScans; }
    static synchronized long verificationBytes() { return verificationBytes; }

    /** Opens one sequential JSONL reader after its descriptor and content have been verified. */
    static Cursor open(String id) {
        JsonObject ref = reference(id);
        Verification verification = verify(id, path(id), ref);
        try {
            return new Cursor(id, ref, verification);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    static List<JsonObject> all(String id) {
        List<JsonObject> rows = new ArrayList<>();
        try (Cursor cursor = open(id)) {
            JsonObject row;
            while ((row = cursor.next()) != null) rows.add(row);
        }
        return rows;
    }

    private static Verification verify(String id, Path file, JsonObject ref) {
        Fingerprint current = fingerprint(file, id);
        synchronized (Artifacts.class) {
            Verification cached = VERIFIED.get(id);
            if (cached != null && cached.fingerprint.equals(current) && cached.matches(ref)) return cached;
        }
        Verification scanned = scan(file, current, ref, id);
        synchronized (Artifacts.class) {
            VERIFIED.put(id, scanned);
            trim(VERIFIED, VERIFY_CACHE_SIZE);
        }
        return scanned;
    }

    private static Verification scan(Path file, Fingerprint before, JsonObject ref, String id) {
        synchronized (Artifacts.class) { verificationScans++; }
        MessageDigest digest = sha256();
        List<Long> offsets = new ArrayList<>();
        long bytePosition = 0;
        long rows = 0;
        long lineStart = 0;
        boolean lineStarted = false;
        boolean pendingCarriageReturn = false;
        byte[] buffer = new byte[8192];
        try (InputStream input = new BufferedInputStream(Files.newInputStream(file))) {
            int length;
            while ((length = input.read(buffer)) != -1) {
                digest.update(buffer, 0, length);
                for (int i = 0; i < length; i++, bytePosition++) {
                    int value = buffer[i] & 0xff;
                    if (pendingCarriageReturn) {
                        pendingCarriageReturn = false;
                        if (value == '\n') {
                            lineStart = bytePosition + 1;
                            continue;
                        }
                    }
                    if (!lineStarted && bytePosition == lineStart && rows % PAGE_SIZE == 0) offsets.add(lineStart);
                    if (value == '\r') {
                        rows++;
                        lineStart = bytePosition + 1;
                        lineStarted = false;
                        pendingCarriageReturn = true;
                    } else if (value == '\n') {
                        rows++;
                        lineStart = bytePosition + 1;
                        lineStarted = false;
                    } else {
                        lineStarted = true;
                    }
                }
            }
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        if (lineStarted) rows++;
        synchronized (Artifacts.class) { verificationBytes += bytePosition; }
        String hash = HexFormat.of().formatHex(digest.digest());
        Fingerprint after = fingerprint(file, id);
        if (!before.equals(after)) throw changedFailure(id);
        if (bytePosition != before.size || bytePosition != bytes(ref) || rows != count(ref) || !hash.equals(ref.get("sha256").getAsString())) {
            throw new IllegalStateException("Artifact integrity failure: truncated or altered " + id);
        }
        return new Verification(before, rows, bytePosition, hash, List.copyOf(offsets));
    }

    private static Fingerprint fingerprint(Path file, String id) {
        try {
            BasicFileAttributes attributes = Files.readAttributes(file, BasicFileAttributes.class);
            if (!attributes.isRegularFile()) throw new IllegalStateException("Invalid artifact file: " + id);
            return new Fingerprint(attributes.size(), attributes.lastModifiedTime(), attributes.fileKey());
        } catch (IOException e) {
            throw new IllegalStateException("Artifact unavailable: " + id, e);
        }
    }

    private static void ensureFingerprint(Path file, Fingerprint expected, String id) {
        if (!expected.equals(fingerprint(file, id))) throw changedFailure(id);
    }

    private static JsonElement parseRow(String line, String id) {
        try {
            return JsonParser.parseString(line);
        } catch (JsonParseException e) {
            throw new IllegalStateException("Artifact row parse failure: " + id, e);
        }
    }

    private static void validateReference(JsonObject ref, String id) {
        if (!ref.has("artifact_id") || !ref.get("artifact_id").isJsonPrimitive()
            || !ref.get("artifact_id").getAsJsonPrimitive().isString() || !id.equals(ref.get("artifact_id").getAsString())) {
            throw new IllegalStateException("Artifact reference identity failure: " + id);
        }
        if (!ref.has("kind") || !ref.get("kind").isJsonPrimitive() || !ref.get("kind").getAsJsonPrimitive().isString()) {
            throw new IllegalStateException("Invalid artifact kind: " + id);
        }
        count(ref);
        bytes(ref);
        if (!ref.has("complete") || !ref.get("complete").isJsonPrimitive()
            || !ref.get("complete").getAsJsonPrimitive().isBoolean() || !ref.get("complete").getAsBoolean()) {
            throw new IllegalStateException("Incomplete artifact reference: " + id);
        }
        if (!ref.has("sha256") || !ref.get("sha256").isJsonPrimitive()
            || !ref.get("sha256").getAsJsonPrimitive().isString() || !ref.get("sha256").getAsString().matches("[0-9a-f]{64}")) {
            throw new IllegalStateException("Invalid artifact hash: " + id);
        }
    }

    private static int count(JsonObject ref) {
        long value = nonnegativeLong(ref, "count");
        if (value > Integer.MAX_VALUE) throw new IllegalStateException("Artifact row count is too large");
        return (int) value;
    }

    private static long bytes(JsonObject ref) {
        return nonnegativeLong(ref, "bytes");
    }

    private static long nonnegativeLong(JsonObject ref, String key) {
        try {
            JsonElement value = ref.get(key);
            if (value == null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isNumber()) throw new NumberFormatException();
            long result = new java.math.BigDecimal(value.getAsString()).longValueExact();
            if (result < 0) throw new NumberFormatException();
            return result;
        } catch (RuntimeException e) {
            throw new IllegalStateException("Invalid artifact " + key);
        }
    }

    private static void requireUuid(String id) {
        if (id == null || !id.matches("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")) {
            throw new IllegalArgumentException("Invalid artifact id");
        }
    }

    private static Path path(String id) {
        requireUuid(id);
        return Path.of("stonebench", "artifacts", id + ".jsonl");
    }

    private static MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException e) {
            throw new AssertionError(e);
        }
    }

    private static IllegalStateException changedFailure(String id) {
        return new IllegalStateException("Artifact integrity failure: attributes changed for " + id);
    }

    private static IllegalStateException rowCountFailure(String id) {
        return new IllegalStateException("Artifact row count failure: " + id);
    }

    private static <T> void trim(LinkedHashMap<String, T> cache, int limit) {
        while (cache.size() > limit) cache.remove(cache.keySet().iterator().next());
    }

    static final class Writer implements AutoCloseable {
        private final String id = UUID.randomUUID().toString();
        private final String kind;
        private final JsonObject metadata;
        private final Path file = path(id);
        private final MessageDigest digest = sha256();
        private final List<Long> offsets = new ArrayList<>();
        private OutputStream output;
        private long count;
        private long bytes;
        private boolean finished;

        private Writer(String kind, JsonObject metadata) throws IOException {
            this.kind = Objects.requireNonNull(kind);
            this.metadata = metadata == null ? new JsonObject() : metadata.deepCopy();
            for (String key : RESERVED) if (this.metadata.has(key)) throw new IllegalArgumentException("Reserved artifact metadata key: " + key);
            Files.createDirectories(file.getParent());
            output = new BufferedOutputStream(Files.newOutputStream(file, StandardOpenOption.CREATE_NEW));
        }

        void add(JsonElement row) {
            if (finished || output == null) throw new IllegalStateException("Artifact writer is closed");
            byte[] encoded = JSON.toJson(row).getBytes(StandardCharsets.UTF_8);
            if (count % PAGE_SIZE == 0) offsets.add(bytes);
            try {
                output.write(encoded);
                output.write('\n');
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
            digest.update(encoded);
            digest.update((byte) '\n');
            bytes += encoded.length + 1L;
            count++;
        }

        JsonObject finish() {
            if (finished) throw new IllegalStateException("Artifact writer already finished");
            try {
                output.close();
                output = null;
                String hash = HexFormat.of().formatHex(digest.digest());
                JsonObject ref = new JsonObject();
                ref.addProperty("artifact_id", id);
                ref.addProperty("kind", kind);
                ref.addProperty("count", count);
                ref.addProperty("sha256", hash);
                ref.addProperty("bytes", bytes);
                ref.addProperty("complete", true);
                for (var entry : metadata.entrySet()) ref.add(entry.getKey(), entry.getValue().deepCopy());
                validateReference(ref, id);
                Path metadataFile = Path.of(file + ".meta");
                Files.writeString(metadataFile, JSON.toJson(ref), StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
                Fingerprint metadataFingerprint = fingerprint(metadataFile, id + " metadata");
                Fingerprint fingerprint = fingerprint(file, id);
                if (fingerprint.size != bytes) throw new IllegalStateException("Artifact write size failure: " + id);
                Verification verification = new Verification(fingerprint, count, bytes, hash, List.copyOf(offsets));
                synchronized (Artifacts.class) {
                    REFERENCES.put(id, new CachedReference(ref.deepCopy(), metadataFingerprint));
                    trim(REFERENCES, VERIFY_CACHE_SIZE);
                    VERIFIED.put(id, verification);
                    trim(VERIFIED, VERIFY_CACHE_SIZE);
                }
                finished = true;
                return ref.deepCopy();
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        }

        @Override public void close() {
            if (finished) return;
            if (output != null) {
                try {
                    output.close();
                } catch (IOException ignored) {
                    // The original write failure is more useful than a second close failure.
                }
                output = null;
            }
            try {
                Files.deleteIfExists(file);
                Files.deleteIfExists(Path.of(file + ".meta"));
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        }
    }

    static final class Cursor implements AutoCloseable {
        private final String id;
        private final int expected;
        private final Fingerprint fingerprint;
        private final BufferedReader lines;
        private int read;
        private boolean eof;
        private boolean closed;

        private Cursor(String id, JsonObject ref, Verification verification) throws IOException {
            this.id = id;
            expected = count(ref);
            fingerprint = verification.fingerprint;
            ensureFingerprint(path(id), fingerprint, id);
            lines = Files.newBufferedReader(path(id), StandardCharsets.UTF_8);
            try {
                ensureFingerprint(path(id), fingerprint, id);
            } catch (RuntimeException e) {
                lines.close();
                throw e;
            }
        }

        JsonObject next() {
            if (closed) throw new IllegalStateException("Artifact cursor is closed");
            if (eof) return null;
            if (read == expected) {
                finishAtEof();
                return null;
            }
            final String line;
            try {
                line = lines.readLine();
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
            if (line == null) throw rowCountFailure(id);
            JsonElement parsed = parseRow(line, id);
            if (!parsed.isJsonObject()) throw new IllegalStateException("Artifact row is not an object: " + id);
            read++;
            if (read == expected) finishAtEof();
            return parsed.getAsJsonObject();
        }

        private void finishAtEof() {
            try {
                if (lines.readLine() != null) throw rowCountFailure(id);
                ensureFingerprint(path(id), fingerprint, id);
                eof = true;
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        }

        @Override public void close() {
            if (closed) return;
            closed = true;
            try {
                lines.close();
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
            ensureFingerprint(path(id), fingerprint, id);
        }
    }

    private record Fingerprint(long size, FileTime modified, Object fileKey) {}

    private record CachedReference(JsonObject ref, Fingerprint fingerprint) {}

    private record Verification(Fingerprint fingerprint, long count, long bytes, String hash, List<Long> offsets) {
        boolean matches(JsonObject ref) {
            return count == Artifacts.count(ref) && bytes == Artifacts.bytes(ref) && hash.equals(ref.get("sha256").getAsString());
        }
    }
}
