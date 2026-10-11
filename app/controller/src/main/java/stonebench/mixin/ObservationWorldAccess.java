package stonebench.mixin;
import it.unimi.dsi.fastutil.objects.ObjectLinkedOpenHashSet;
import net.minecraft.server.world.*;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;
@Mixin(ServerWorld.class)
public interface ObservationWorldAccess {
    @Accessor("syncedBlockEventQueue") ObjectLinkedOpenHashSet<BlockEvent> stonebench$blockEvents();
}
