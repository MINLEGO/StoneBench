package stonebench.mixin;
import com.google.gson.JsonObject;
import net.minecraft.block.BlockState;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.BlockPos;
import net.minecraft.world.World;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import stonebench.Observation;
@Mixin(World.class)
public class ObservationWritesMixin {
    @Inject(method="setBlockState(Lnet/minecraft/util/math/BlockPos;Lnet/minecraft/block/BlockState;II)Z",at=@At("HEAD"))
    private void write(BlockPos pos,BlockState state,int flags,int depth,CallbackInfoReturnable<Boolean> ci) {
        if((Object)this instanceof ServerWorld world) {JsonObject detail=new JsonObject();detail.addProperty("before",world.getBlockState(pos).toString());detail.addProperty("requested",state.toString());detail.addProperty("flags",flags);detail.addProperty("depth",depth);Observation.event(world,"block_write_requested",pos,detail);}
    }
    @Inject(method="setBlockState(Lnet/minecraft/util/math/BlockPos;Lnet/minecraft/block/BlockState;II)Z",at=@At("RETURN"))
    private void written(BlockPos pos,BlockState state,int flags,int depth,CallbackInfoReturnable<Boolean> ci) {
        if((Object)this instanceof ServerWorld world) {JsonObject detail=new JsonObject();detail.addProperty("effective",world.getBlockState(pos).toString());detail.addProperty("changed",ci.getReturnValue());Observation.event(world,"block_write_result",pos,detail);if(ci.getReturnValue()) Observation.changedBlock(world,pos);}
    }
}

