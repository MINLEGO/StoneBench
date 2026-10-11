package stonebench.mixin;
import com.google.gson.JsonObject;
import net.minecraft.block.*;
import net.minecraft.server.world.*;
import net.minecraft.util.math.BlockPos;
import net.minecraft.world.block.WireOrientation;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.*;
import stonebench.*;
@Mixin(ServerWorld.class)
public class ObservationEventsMixin {
    @Inject(method="tickTime",at=@At("HEAD")) private void time(CallbackInfo ci) {Controller.observationPhase("before_world_time");}
    @Inject(method="tickTime",at=@At("RETURN")) private void timed(CallbackInfo ci) {Controller.observationPhase("world_tick");}
    @Inject(method="processSyncedBlockEvents",at=@At("HEAD")) private void blockEvents(CallbackInfo ci) {Controller.observationPhase("block_events");}
    @Inject(method="processSyncedBlockEvents",at=@At("RETURN")) private void afterEvents(CallbackInfo ci) {Controller.observationPhase("block_entity_tick");}
    @Inject(method="addSyncedBlockEvent",at=@At("HEAD"))
    private void queued(BlockPos pos,Block block,int type,int data,CallbackInfo ci) {JsonObject detail=Observation.detail("block",net.minecraft.registry.Registries.BLOCK.getId(block).toString());detail.addProperty("type",type);detail.addProperty("data",data);Observation.event((ServerWorld)(Object)this,"block_event_enqueued",pos,detail);}
    @Inject(method="processBlockEvent",at=@At(value="INVOKE",target="Lnet/minecraft/block/BlockState;onSyncedBlockEvent(Lnet/minecraft/world/World;Lnet/minecraft/util/math/BlockPos;II)Z"))
    private void executed(BlockEvent event,CallbackInfoReturnable<Boolean> ci) {JsonObject detail=Observation.detail("block",net.minecraft.registry.Registries.BLOCK.getId(event.block()).toString());detail.addProperty("type",event.type());detail.addProperty("data",event.data());Observation.event((ServerWorld)(Object)this,"block_event_callback",event.pos(),detail);}
    @Inject(method="updateNeighbor(Lnet/minecraft/util/math/BlockPos;Lnet/minecraft/block/Block;Lnet/minecraft/world/block/WireOrientation;)V",at=@At("HEAD"))
    private void neighbor(BlockPos pos,Block source,WireOrientation orientation,CallbackInfo ci) {Observation.event((ServerWorld)(Object)this,"neighbor_update",pos,Observation.detail("source",net.minecraft.registry.Registries.BLOCK.getId(source).toString()));}
    @Inject(method="updateNeighbor(Lnet/minecraft/block/BlockState;Lnet/minecraft/util/math/BlockPos;Lnet/minecraft/block/Block;Lnet/minecraft/world/block/WireOrientation;Z)V",at=@At("HEAD"))
    private void stateNeighbor(BlockState state,BlockPos pos,Block source,WireOrientation orientation,boolean notify,CallbackInfo ci) {Observation.event((ServerWorld)(Object)this,"neighbor_state_update",pos,Observation.detail("source",net.minecraft.registry.Registries.BLOCK.getId(source).toString()));}
    @Inject(method="tickBlock",at=@At("HEAD")) private void blockTick(BlockPos pos,Block block,CallbackInfo ci) {Controller.observationPhase("scheduled_block_ticks");Observation.event((ServerWorld)(Object)this,"scheduled_block_tick",pos,Observation.detail("block",net.minecraft.registry.Registries.BLOCK.getId(block).toString()));}
    @Inject(method="tickFluid",at=@At("HEAD")) private void fluidTick(BlockPos pos,net.minecraft.fluid.Fluid fluid,CallbackInfo ci) {Controller.observationPhase("scheduled_fluid_ticks");Observation.event((ServerWorld)(Object)this,"scheduled_fluid_tick",pos,Observation.detail("fluid",net.minecraft.registry.Registries.FLUID.getId(fluid).toString()));}
}
