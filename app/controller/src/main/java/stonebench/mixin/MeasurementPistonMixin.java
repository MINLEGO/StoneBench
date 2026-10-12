package stonebench.mixin;

import net.minecraft.block.BlockState;
import net.minecraft.block.entity.PistonBlockEntity;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.BlockPos;
import net.minecraft.world.World;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import stonebench.Observation;

@Mixin(PistonBlockEntity.class)
public class MeasurementPistonMixin {
    @Inject(method="setWorld",at=@At("RETURN"))
    private void started(World world,CallbackInfo ci) {
        if(world instanceof ServerWorld server) Observation.pistonSample(server,((PistonBlockEntity)(Object)this).getPos(),(PistonBlockEntity)(Object)this,"start");
    }
    @Inject(method="tick",at=@At("HEAD"))
    private static void before(World world,BlockPos pos,BlockState state,PistonBlockEntity entity,CallbackInfo ci) {
        if(world instanceof ServerWorld server) Observation.pistonSample(server,pos,entity,"before_tick");
    }
    @Inject(method="tick",at=@At("RETURN"))
    private static void after(World world,BlockPos pos,BlockState state,PistonBlockEntity entity,CallbackInfo ci) {
        if(world instanceof ServerWorld server) Observation.pistonSample(server,pos,entity,"after_tick");
    }
    @Inject(method="finish",at=@At("HEAD"))
    private void finish(CallbackInfo ci) {
        PistonBlockEntity entity=(PistonBlockEntity)(Object)this;
        if(entity.getWorld() instanceof ServerWorld server) Observation.pistonSample(server,entity.getPos(),entity,"forced_finish");
    }
    @Inject(method="finish",at=@At("RETURN"))
    private void finished(CallbackInfo ci) {
        PistonBlockEntity entity=(PistonBlockEntity)(Object)this;
        if(entity.getWorld() instanceof ServerWorld server) Observation.pistonSample(server,entity.getPos(),entity,"after_forced_finish");
    }

}
