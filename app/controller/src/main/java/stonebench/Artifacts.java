package stonebench;

import com.google.gson.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;

/** Immutable JSONL artifacts. Pages carry counts and an integrity hash, never an implicit limit. */
final class Artifacts {
    private static final Gson JSON=new GsonBuilder().serializeNulls().disableHtmlEscaping().create();
    private static final Map<String,JsonObject> REFERENCES=new HashMap<>();
    static JsonObject write(String kind,Collection<? extends JsonElement> rows) {return write(kind,rows,new JsonObject());}
    static JsonObject write(String kind,Collection<? extends JsonElement> rows,JsonObject metadata) {
        try {
            String id=UUID.randomUUID().toString();Path path=path(id);Files.createDirectories(path.getParent());
            try(var writer=Files.newBufferedWriter(path,StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW)) {
                for(JsonElement row:rows) {writer.write(JSON.toJson(row));writer.newLine();}
            }
            JsonObject ref=new JsonObject();ref.addProperty("artifact_id",id);ref.addProperty("kind",kind);ref.addProperty("count",rows.size());
            ref.addProperty("sha256",hash(path));ref.addProperty("bytes",Files.size(path));ref.addProperty("complete",true);
            for(var entry:metadata.entrySet()) ref.add(entry.getKey(),entry.getValue());
            Files.writeString(Path.of(path+".meta"),JSON.toJson(ref),StandardOpenOption.CREATE_NEW);
            REFERENCES.put(id,ref);return ref.deepCopy();
        } catch(IOException e) {throw new UncheckedIOException(e);}
    }
    static JsonObject read(JsonObject args) {
        String id=Task.string(args,"artifact_id");JsonObject ref=reference(id);
        int count=ref.get("count").getAsInt(),offset=Task.integer(args,"offset",0,count),limit=Task.integer(args,"limit",1,256);
        try {
            if(!hash(path(id)).equals(ref.get("sha256").getAsString())) throw new IllegalStateException("Artifact integrity failure: truncated or altered "+id);
            JsonArray entries=new JsonArray();try(var lines=Files.lines(path(id),StandardCharsets.UTF_8)) {lines.skip(offset).limit(limit).forEach(line->entries.add(JsonParser.parseString(line)));}
            if(entries.size()!=Math.min(limit,count-offset)) throw new IllegalStateException("Artifact row count failure");
            JsonObject result=new JsonObject();result.add("artifact",ref.deepCopy());result.add("entries",entries);result.addProperty("offset",offset);
            int next=offset+entries.size();result.add("next_offset",next<count?new JsonPrimitive(next):JsonNull.INSTANCE);result.addProperty("complete",next==count);return result;
        } catch(IOException e) {throw new UncheckedIOException(e);}
    }
    static JsonObject reference(String id) {
        if(!id.matches("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")) throw new IllegalArgumentException("Invalid artifact id");
        if(!REFERENCES.containsKey(id)) try {REFERENCES.put(id,JsonParser.parseString(Files.readString(Path.of(path(id)+".meta"))).getAsJsonObject());}
        catch(IOException e) {throw new IllegalArgumentException("Unknown artifact in this attempt");}
        return REFERENCES.get(id).deepCopy();
    }
    static List<JsonObject> all(String id) {
        List<JsonObject> rows=new ArrayList<>();int offset=0;
        do {JsonObject args=new JsonObject();args.addProperty("artifact_id",id);args.addProperty("offset",offset);args.addProperty("limit",256);JsonObject page=read(args);for(var row:page.getAsJsonArray("entries")) rows.add(row.getAsJsonObject());if(page.get("next_offset").isJsonNull()) break;offset=page.get("next_offset").getAsInt();} while(true);
        return rows;
    }
    private static Path path(String id) {return Path.of("stonebench","artifacts",id+".jsonl");}
    private static String hash(Path path) throws IOException {
        try {MessageDigest digest=MessageDigest.getInstance("SHA-256");try(var input=Files.newInputStream(path)) {byte[] b=new byte[8192];int n;while((n=input.read(b))!=-1) digest.update(b,0,n);}return HexFormat.of().formatHex(digest.digest());}
        catch(NoSuchAlgorithmException e) {throw new AssertionError(e);}
    }
}
