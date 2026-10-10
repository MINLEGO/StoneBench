package stonebench.mixin;
import net.minecraft.block.Block;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.math.Direction;
import net.minecraft.world.block.WireOrientation;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import stonebench.Construction;
@Mixin(ServerWorld.class)
public abstract class ConstructionNotificationsMixin {
    @Inject(method="updateNeighbors",at=@At("HEAD"))
    private void stonebench$notify(BlockPos pos,Block block,CallbackInfo ci) {Construction.observe("notify_neighbors",pos);}
    @Inject(method="updateNeighborsAlways",at=@At("HEAD"))
    private void stonebench$always(BlockPos pos,Block block,WireOrientation orientation,CallbackInfo ci) {Construction.observe("notify_neighbors_always",pos);}
    @Inject(method="updateNeighborsExcept",at=@At("HEAD"))
    private void stonebench$except(BlockPos pos,Block block,Direction direction,WireOrientation orientation,CallbackInfo ci) {Construction.observe("notify_neighbors_except",pos);}
}
