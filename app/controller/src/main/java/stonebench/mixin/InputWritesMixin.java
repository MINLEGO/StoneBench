package stonebench.mixin;
import net.minecraft.block.BlockState;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.BlockPos;
import net.minecraft.world.World;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import stonebench.Inputs;
@Mixin(World.class)
public class InputWritesMixin {
    @Inject(method="setBlockState(Lnet/minecraft/util/math/BlockPos;Lnet/minecraft/block/BlockState;II)Z",at=@At("RETURN")) private void changed(BlockPos pos,BlockState state,int flags,int depth,CallbackInfoReturnable<Boolean> ci) {if((Object)this instanceof ServerWorld world) Inputs.changed(world);}
}
