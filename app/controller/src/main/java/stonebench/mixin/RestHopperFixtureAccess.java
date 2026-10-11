package stonebench.mixin;
import net.minecraft.block.entity.HopperBlockEntity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;
@Mixin(HopperBlockEntity.class)
public interface RestHopperFixtureAccess {
    @Accessor("transferCooldown") void stonebench$fixtureCooldown(int value);
}
