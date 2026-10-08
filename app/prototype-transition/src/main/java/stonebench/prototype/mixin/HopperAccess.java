package stonebench.prototype.mixin;

import net.minecraft.block.entity.HopperBlockEntity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(HopperBlockEntity.class)
public interface HopperAccess {
    @Accessor("lastTickTime") long transitionLastTickTime();
    @Accessor("transferCooldown") int transitionCooldown();
    @Accessor("transferCooldown") void transitionCooldown(int ticks);
}
