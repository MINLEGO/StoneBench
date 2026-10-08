package stonebench.prototype.mixin;

import net.minecraft.server.MinecraftServer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import stonebench.prototype.Experiment;

@Mixin(MinecraftServer.class)
public class ServerMixin {
    // Freeze before world loading, rather than racing the startup "Done" message.
    @Inject(method = "loadWorld", at = @At("HEAD"))
    private void freezeBeforeLoad(CallbackInfo ci) {
        ((MinecraftServer) (Object) this).getTickManager().setFrozen(true);
    }
    @Inject(method = "loadWorld", at = @At("RETURN"))
    private void readyAfterLoad(CallbackInfo ci) { Experiment.ready(); }
    @Inject(method = "tickWorlds", at = @At("RETURN"))
    private void recordTick(CallbackInfo ci) { Experiment.afterTick((MinecraftServer) (Object) this); }
}
