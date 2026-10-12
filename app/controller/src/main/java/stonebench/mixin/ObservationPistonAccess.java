package stonebench.mixin;
import net.minecraft.block.entity.PistonBlockEntity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;
import org.spongepowered.asm.mixin.gen.Invoker;
import net.minecraft.block.BlockState;
@Mixin(PistonBlockEntity.class)
public interface ObservationPistonAccess {
    @Invoker("getHeadBlockState") BlockState stonebench$headBlockState();
    @Accessor("progress") float stonebench$progress();
    @Accessor("lastProgress") float stonebench$lastProgress();
    @Accessor("savedWorldTime") long stonebench$savedWorldTime();
}
