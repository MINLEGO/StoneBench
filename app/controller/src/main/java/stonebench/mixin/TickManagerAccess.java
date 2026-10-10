package stonebench.mixin;

import net.minecraft.world.tick.TickManager;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(TickManager.class)
public interface TickManagerAccess {
    // Vanilla caches this before tickWorlds; stopStepping alone cannot revoke that tick.
    @Accessor("shouldTick") void stonebench$shouldTick(boolean value);
}
