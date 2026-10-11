package stonebench.mixin;
import net.minecraft.block.BlockState;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.BlockPos;
import net.minecraft.world.World;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import stonebench.Observation;
@Mixin(World.class)
public class ObservationReadsMixin {
    @Inject(method="getBlockState",at=@At("RETURN"))
    private void read(BlockPos pos,CallbackInfoReturnable<BlockState> ci) {
        if((Object)this instanceof ServerWorld world) Observation.read(world,pos,ci.getReturnValue());
    }
}
