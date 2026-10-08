package stonebench.prototype.mixin;

import com.mojang.brigadier.CommandDispatcher;
import net.minecraft.server.command.CommandManager;
import net.minecraft.server.command.ServerCommandSource;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import stonebench.prototype.Experiment;

@Mixin(CommandManager.class)
public class CommandMixin {
    @Shadow @Final private CommandDispatcher<ServerCommandSource> dispatcher;
    @Inject(method = "<init>", at = @At("RETURN"))
    private void register(CallbackInfo ci) { Experiment.register(dispatcher); }
}
