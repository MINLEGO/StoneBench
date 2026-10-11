package stonebench.mixin;
import net.minecraft.server.world.ServerWorld;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import stonebench.Inputs;
@Mixin(ServerWorld.class)
public class InputTimeMixin {
    @Inject(method="tickTime",at=@At("HEAD")) private void input(CallbackInfo ci) {Inputs.beforeTime((ServerWorld)(Object)this);}
}
