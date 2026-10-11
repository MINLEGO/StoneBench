package stonebench.mixin;
import com.google.gson.JsonObject;
import net.minecraft.world.tick.*;
import net.minecraft.block.Block;
import net.minecraft.fluid.Fluid;
import net.minecraft.registry.Registries;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import stonebench.*;
@Mixin(WorldTickScheduler.class)
public class ObservationSchedulingMixin<T> {
    @Inject(method="scheduleTick(Lnet/minecraft/world/tick/OrderedTick;)V",at=@At("HEAD"))
    private void schedule(OrderedTick<T> tick,CallbackInfo ci) {
        var world=Controller.world();if(world==null || ((Object)this!=world.getBlockTickScheduler() && (Object)this!=world.getFluidTickScheduler())) return;
        JsonObject detail=new JsonObject();Object type=tick.type();detail.addProperty("type",type instanceof Block block?Registries.BLOCK.getId(block).toString():Registries.FLUID.getId((Fluid)type).toString());detail.addProperty("trigger_tick",tick.triggerTick());detail.addProperty("priority",tick.priority().getIndex());detail.addProperty("sub_tick_order",tick.subTickOrder());
        Observation.event(world,type instanceof Block?"block_tick_schedule_requested":"fluid_tick_schedule_requested",tick.pos(),detail);
    }
}
