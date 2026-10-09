package stonebench.prototype.mixin;

import net.minecraft.server.world.ServerWorld;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import stonebench.prototype.Experiment;

@Mixin(ServerWorld.class)
public class InputMixin {
    // MC-172213: inject before world time increments, only on active simulation ticks.
    @Inject(method = "tickTime", at = @At("HEAD"))
    private void input(CallbackInfo ci) { Experiment.beforeTime((ServerWorld) (Object) this); }
}
