package stonebench.prototype.mixin;

import net.minecraft.block.BlockState;
import net.minecraft.world.World;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.BlockPos;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import stonebench.prototype.Experiment;

@Mixin(World.class)
public class StateMixin {
    @Inject(method = "setBlockState(Lnet/minecraft/util/math/BlockPos;Lnet/minecraft/block/BlockState;II)Z", at = @At("RETURN"))
    private void changed(BlockPos pos, BlockState state, int flags, int depth, CallbackInfoReturnable<Boolean> ci) {
        if ((Object) this instanceof ServerWorld world && ci.getReturnValue()) Experiment.changed(world, pos);
    }
}
