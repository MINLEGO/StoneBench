package stonebench;

import com.google.gson.*;
import net.minecraft.nbt.*;

/** SNBT scalars preserve exact longs, float suffixes and array types without JSON number coercion. */
public final class TypedNbt {
    public static JsonObject encode(NbtElement value) {
        JsonObject result=new JsonObject(); result.addProperty("type",value.getType());
        if(value instanceof NbtCompound compound) {
            JsonObject entries=new JsonObject();
            compound.getKeys().stream().sorted().forEach(key->entries.add(key,encode(compound.get(key))));
            result.add("value",entries);
        } else if(value instanceof NbtList list) {
            JsonArray entries=new JsonArray();list.forEach(item->entries.add(encode(item)));result.add("value",entries);
        } else result.addProperty("value",value.toString());
        return result;
    }
}
