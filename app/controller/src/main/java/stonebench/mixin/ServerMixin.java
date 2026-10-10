package stonebench.mixin;

import net.minecraft.server.MinecraftServer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import stonebench.Controller;

@Mixin(MinecraftServer.class)
public class ServerMixin {
    @Inject(method="loadWorld", at=@At("HEAD"))
    private void freeze(CallbackInfo ci) { ((MinecraftServer)(Object)this).getTickManager().setFrozen(true); }
    @Inject(method="loadWorld", at=@At("RETURN"))
    private void ready(CallbackInfo ci) { Controller.boot((MinecraftServer)(Object)this); }
    @Inject(method="tickWorlds", at=@At("HEAD"))
    private void before(CallbackInfo ci) { Controller.beforeTick(); }
    @Inject(method="tickWorlds", at=@At("RETURN"))
    private void after(CallbackInfo ci) { Controller.afterTick(); }
    @Inject(method="shutdown", at=@At("HEAD"))
    private void shutdown(CallbackInfo ci) { Controller.shutdown(); }
}
