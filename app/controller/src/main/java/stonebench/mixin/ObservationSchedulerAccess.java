package stonebench.mixin;
import it.unimi.dsi.fastutil.longs.Long2ObjectMap;
import net.minecraft.world.tick.*;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;
@Mixin(WorldTickScheduler.class)
public interface ObservationSchedulerAccess<T> {
    @Accessor("chunkTickSchedulers") Long2ObjectMap<ChunkTickScheduler<T>> stonebench$schedulers();
}
