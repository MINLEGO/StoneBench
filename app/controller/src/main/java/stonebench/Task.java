package stonebench;

import com.google.gson.*;
import java.math.BigDecimal;
import java.util.*;

/** Immutable task geometry; construction scope can be enlarged by later tools. */
public final class Task {
    public static final String RULES = "https://docs.google.com/document/d/1kDNXIvQ8uAMU5qRFXIk6nLxbVliIjcMu1MjHjLJrRH4/edit";
    public static int integer(JsonObject args, String name, int min, int max) {
        JsonElement value = args.get(name);
        if (value == null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isNumber())
            throw new IllegalArgumentException(name + " must be an integer number");
        try {
            int result = new BigDecimal(value.getAsString()).intValueExact();
            if (result < min || result > max) throw new ArithmeticException();
            return result;
        } catch (ArithmeticException | NumberFormatException e) {
            throw new IllegalArgumentException(name + " must be an integer in " + min + ".." + max);
        }
    }
    public static String string(JsonObject args, String name) {
        JsonElement value = args.get(name);
        if (value == null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isString())
            throw new IllegalArgumentException(name + " must be a string");
        return value.getAsString();
    }
    public static JsonObject describe(String id, Integer budget) {
        if (!id.matches("[2-5]x[2-5]-(volume|speed)") || id.charAt(0) != id.charAt(2))
            throw new IllegalArgumentException("Unknown task_id");
        int size = id.charAt(0) - '0';
        JsonObject task = new JsonObject();
        task.addProperty("task_id", id); task.addProperty("minecraft", "1.21.11");
        task.addProperty("category", "regular DOOR"); task.addProperty("width", size); task.addProperty("height", size);
        task.addProperty("objective", id.endsWith("volume") ? "minimize_volume" : "minimize_opening_ticks");
        task.addProperty("budget_tokens", budget);
        JsonObject basis = new JsonObject();
        basis.add("origin", position(1024,80,1024)); basis.addProperty("vertical_axis", "+Y");
        basis.addProperty("horizontal_axis", "+X"); basis.addProperty("normal", "+Z");
        task.add("passage", basis);
        JsonArray frame = new JsonArray();
        for (int y=0;y<size;y++) for (int x=0;x<size;x++) frame.add(position(1024+x,80+y,1024));
        task.add("expected_frame", frame);
        JsonObject scope = new JsonObject(); scope.add("min", position(1024,64,1024)); scope.add("max", position(1039,111,1039));
        scope.addProperty("meaning", "initial prepared observation scope; not a conformity boundary");
        task.add("prepared_region", scope);
        return task;
    }
    /** A task persisted by an earlier build may still carry the rules link; the agent never receives it. */
    public static JsonObject restored(JsonObject persisted) {JsonObject task=persisted.deepCopy();task.remove("rules_reference");return task;}
    public static JsonObject position(int x,int y,int z) { JsonObject p=new JsonObject();p.addProperty("x",x);p.addProperty("y",y);p.addProperty("z",z);return p; }
}
