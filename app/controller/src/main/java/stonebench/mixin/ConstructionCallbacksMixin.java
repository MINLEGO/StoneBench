package stonebench.mixin;
import net.minecraft.block.BlockState;
import net.minecraft.block.AbstractBlock;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.BlockPos;
import net.minecraft.world.World;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import stonebench.Construction;
@Mixin(AbstractBlock.AbstractBlockState.class)
public abstract class ConstructionCallbacksMixin {
    @Inject(method="onBlockAdded",at=@At("HEAD"))
    private void stonebench$added(World world,BlockPos pos,BlockState old,boolean moved,CallbackInfo ci) {Construction.observe("on_block_added",pos);}
    @Inject(method="onStateReplaced",at=@At("HEAD"))
    private void stonebench$replaced(ServerWorld world,BlockPos pos,boolean moved,CallbackInfo ci) {Construction.observe("on_state_replaced",pos);}
}
