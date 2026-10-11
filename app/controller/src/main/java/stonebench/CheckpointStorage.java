package stonebench;

import com.google.gson.*;
import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.time.Instant;
import java.util.*;

/** Controller-owned immutable world copies, with content verification before publication/reprise. */
public final class CheckpointStorage {
    private static final Gson JSON=new GsonBuilder().serializeNulls().disableHtmlEscaping().create();
    private final Path root;

    public CheckpointStorage(Path root) {this.root=root.toAbsolutePath().normalize();}

    public JsonObject create(Path world,JsonObject context,JsonObject state,JsonObject provenance) throws IOException {
        Files.createDirectories(root);
        if(Files.isSymbolicLink(root) || !Files.isDirectory(root,LinkOption.NOFOLLOW_LINKS)) throw new IOException("Unsafe checkpoint store");
        String id=UUID.randomUUID().toString();
        Path partial=root.resolve(".partial-"+id),destination=root.resolve(id);
        Files.createDirectory(partial);
        try {
            Map<String,String> before=hashes(world,true);
            if(!before.containsKey("level.dat")) throw new IOException("Flushed world has no level.dat");
            copy(world,partial.resolve("world"),true);
            if(!before.equals(hashes(world,true)) || !before.equals(hashes(partial.resolve("world"),true)))
                throw new IOException("World changed during frozen checkpoint copy");
            write(partial.resolve("context.json"),context);
            write(partial.resolve("state.json"),state);
            JsonObject manifest=new JsonObject();manifest.addProperty("format",1);manifest.addProperty("checkpoint_id",id);
            manifest.addProperty("created_at",Instant.now().toString());manifest.add("provenance",provenance.deepCopy());
            manifest.addProperty("world_copy","save(flush=true) while frozen; matching source/copy/source SHA-256 maps");
            manifest.addProperty("session_lock","excluded; recreated by the next Minecraft process");
            JsonObject files=new JsonObject();hashes(partial,false).forEach(files::addProperty);manifest.add("files",files);
            write(partial.resolve("manifest.json"),manifest);
            Files.move(partial,destination,StandardCopyOption.ATOMIC_MOVE);
            return descriptor(id);
        } finally {
            if(Files.exists(partial)) deleteOwned(partial);
        }
    }

    public JsonArray list() throws IOException {
        JsonArray result=new JsonArray();if(!Files.exists(root)) return result;
        try(var paths=Files.list(root)) {
            for(Path path:paths.sorted().toList()) {
                if(path.getFileName().toString().startsWith(".partial-")) continue;
                if(!Files.isDirectory(path,LinkOption.NOFOLLOW_LINKS)) throw new IOException("Unexpected checkpoint store entry: "+path);
                result.add(descriptor(path.getFileName().toString()));
            }
        }
        return result;
    }

    public JsonObject descriptor(String id) throws IOException {
        Path directory=directory(id);JsonObject manifest=read(directory.resolve("manifest.json"));
        if(manifest.get("format").getAsInt()!=1 || !id.equals(manifest.get("checkpoint_id").getAsString())) throw new IOException("Checkpoint manifest identity mismatch");
        JsonObject expected=manifest.getAsJsonObject("files");Map<String,String> actual=hashes(directory,false);actual.remove("manifest.json");
        if(expected==null || actual.size()!=expected.size()) throw new IOException("Checkpoint file set changed: "+id);
        for(var entry:actual.entrySet()) {
            if(!expected.has(entry.getKey()) || !entry.getValue().equals(expected.get(entry.getKey()).getAsString()))
                throw new IOException("Checkpoint SHA-256 mismatch: "+id+"/"+entry.getKey());
        }
        JsonObject result=manifest.deepCopy();result.addProperty("manifest_sha256",hash(directory.resolve("manifest.json")));
        result.addProperty("verified",true);return result;
    }

    public JsonObject context(String id) throws IOException {descriptor(id);return read(directory(id).resolve("context.json"));}
    public JsonObject state(String id) throws IOException {descriptor(id);return read(directory(id).resolve("state.json"));}

    /** Only writes a request. The owning supervisor applies it after its server process has exited. */
    public JsonObject requestRestore(String id,Path serverRoot,String attemptId) throws IOException {
        JsonObject checkpoint=descriptor(id),context=context(id);
        if(!attemptId.equals(context.get("attempt_id").getAsString())) throw new IllegalArgumentException("Checkpoint belongs to another attempt");
        Path control=serverRoot.toAbsolutePath().normalize().resolve("stonebench");
        JsonObject request=new JsonObject();request.addProperty("request_id",UUID.randomUUID().toString());request.addProperty("checkpoint_id",id);
        request.addProperty("attempt_id",attemptId);request.addProperty("manifest_sha256",checkpoint.get("manifest_sha256").getAsString());
        request.addProperty("status","restart_required");request.addProperty("mutates_attempt",true);
        Path pending=control.resolve("restore-request.json");if(Files.exists(pending)) throw new IllegalStateException("A restore is already pending");
        writeAtomic(pending,request);
        return request;
    }

    private Path directory(String id) throws IOException {
        try {if(!UUID.fromString(id).toString().equals(id)) throw new IllegalArgumentException();}
        catch(RuntimeException e) {throw new IllegalArgumentException("checkpoint_id must be a canonical UUID");}
        Path directory=root.resolve(id);
        if(Files.isSymbolicLink(root) || Files.isSymbolicLink(directory) || !Files.isDirectory(directory,LinkOption.NOFOLLOW_LINKS)) throw new IOException("Missing or unsafe checkpoint: "+id);
        return directory;
    }

    static JsonObject read(Path path) throws IOException {
        if(Files.isSymbolicLink(path)) throw new IOException("Checkpoint file is a symlink: "+path);
        try {return JsonParser.parseString(Files.readString(path)).getAsJsonObject();}
        catch(RuntimeException e) {throw new IOException("Invalid checkpoint JSON: "+path,e);}
    }

    static void writeAtomic(Path path,JsonObject value) throws IOException {
        Path partial=path.resolveSibling(path.getFileName()+".partial-"+UUID.randomUUID());
        try {write(partial,value);Files.move(partial,path,StandardCopyOption.ATOMIC_MOVE);}
        finally {Files.deleteIfExists(partial);}
    }

    private static void write(Path path,JsonObject value) throws IOException {
        Files.writeString(path,JSON.toJson(value),StandardOpenOption.CREATE_NEW);
    }

    static String hash(Path path) throws IOException {
        try {
            MessageDigest digest=MessageDigest.getInstance("SHA-256");
            try(InputStream input=Files.newInputStream(path)) {byte[] buffer=new byte[65536];int n;while((n=input.read(buffer))!=-1) digest.update(buffer,0,n);}
            return HexFormat.of().formatHex(digest.digest());
        } catch(NoSuchAlgorithmException e) {throw new IllegalStateException(e);}
    }

    private static Map<String,String> hashes(Path directory,boolean excludeLock) throws IOException {
        Map<String,String> result=new TreeMap<>();
        if(Files.isSymbolicLink(directory) || !Files.isDirectory(directory)) throw new IOException("Invalid copy directory: "+directory);
        try(var paths=Files.walk(directory)) {
            for(Path path:paths.sorted().toList()) {
                if(excludeLock && path.getFileName().toString().equals("session.lock")) continue;
                if(Files.isSymbolicLink(path)) throw new IOException("Cannot checkpoint symlink: "+path);
                if(Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS)) result.put(directory.relativize(path).toString().replace('\\','/'),hash(path));
                else if(!Files.isDirectory(path,LinkOption.NOFOLLOW_LINKS)) throw new IOException("Unexpected checkpoint file type: "+path);
            }
        }
        return result;
    }

    private static void copy(Path source,Path target,boolean excludeLock) throws IOException {
        try(var paths=Files.walk(source)) {
            for(Path path:paths.sorted().toList()) {
                if(excludeLock && path.getFileName().toString().equals("session.lock")) continue;
                Path destination=target.resolve(source.relativize(path));
                if(Files.isDirectory(path,LinkOption.NOFOLLOW_LINKS)) Files.createDirectories(destination);
                else Files.copy(path,destination);
            }
        }
    }

    private void deleteOwned(Path directory) throws IOException {
        if(!directory.getParent().equals(root) || !directory.getFileName().toString().startsWith(".partial-")) throw new IOException("Refusing cleanup outside owned partial checkpoint");
        try(var paths=Files.walk(directory)) {for(Path path:paths.sorted(Comparator.reverseOrder()).toList()) Files.delete(path);}
    }
}
