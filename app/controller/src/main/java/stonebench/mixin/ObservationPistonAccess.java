package stonebench.mixin;
import net.minecraft.block.entity.PistonBlockEntity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;
@Mixin(PistonBlockEntity.class)
public interface ObservationPistonAccess {
    @Accessor("progress") float stonebench$progress();
    @Accessor("lastProgress") float stonebench$lastProgress();
    @Accessor("savedWorldTime") long stonebench$savedWorldTime();
}
