package stonebench.mixin;
import net.minecraft.block.PistonBlock;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.*;
import net.minecraft.world.RedstoneView;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import stonebench.Observation;
@Mixin(PistonBlock.class)
public class MeasurementPowerMixin {
    @Inject(method="shouldExtend",at=@At("RETURN"))
    private void power(RedstoneView world,BlockPos pos,Direction facing,CallbackInfoReturnable<Boolean> ci) {
        if(world instanceof ServerWorld server) {
            var detail=Observation.detail("facing",facing.asString());detail.addProperty("powered",ci.getReturnValue());
            Observation.event(server,"piston_received_power",pos,detail);
        }
    }
}
