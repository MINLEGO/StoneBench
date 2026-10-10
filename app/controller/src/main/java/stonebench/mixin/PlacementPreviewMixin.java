package stonebench.mixin;
import net.minecraft.block.BlockState;
import net.minecraft.block.Block;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import net.minecraft.util.math.BlockPos;
import net.minecraft.world.World;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import stonebench.Construction;
@Mixin(World.class)
public abstract class PlacementPreviewMixin {
    @Inject(method="updateComparators",at=@At("HEAD"),cancellable=true)
    private void stonebench$comparator(BlockPos pos,Block block,CallbackInfo ci) {
        if(Construction.deferComparatorUpdate()) ci.cancel();else Construction.observe("update_comparators",pos);
    }
    @Inject(method="getBlockState",at=@At("HEAD"),cancellable=true)
    private void stonebench$preview(BlockPos pos,CallbackInfoReturnable<BlockState> result) {
        BlockState state=Construction.previewState(pos);if(state!=null) result.setReturnValue(state);
    }
}
