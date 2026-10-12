package stonebench;

import com.google.gson.*;
import net.minecraft.block.*;
import net.minecraft.block.entity.PistonBlockEntity;
import net.minecraft.registry.Registries;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.*;
import stonebench.mixin.ObservationPistonAccess;

/** Physical extents and vanilla movement samples; decisions belong to the sourced report. */
public final class Measurement {
    private Measurement() {}
    public static JsonObject block(ServerWorld world,BlockPos pos,BlockState state) {
        JsonObject row=Task.position(pos.getX(),pos.getY(),pos.getZ());
        row.addProperty("block",Registries.BLOCK.getId(state.getBlock()).toString());
        var shape=state.getOutlineShape(world,pos);
        if(!shape.isEmpty()) row.add("bounds",box(shape.getBoundingBox().offset(pos)));
        // Supports/components cannot become excluded merely by being on the frame perimeter.
        boolean component=state.emitsRedstonePower() || state.getBlock() instanceof PistonBlock || state.isOf(Blocks.PISTON_HEAD) || state.isOf(Blocks.MOVING_PISTON) || world.getBlockEntity(pos)!=null;
        row.addProperty("wiring_role",component?"component":"passive_material");
        return row;
    }
    public static JsonArray box(Box box) {
        JsonArray result=new JsonArray();for(double value:new double[]{box.minX,box.minY,box.minZ,box.maxX,box.maxY,box.maxZ}) result.add(value);return result;
    }
    public static void piston(ServerWorld world,BlockPos pos,PistonBlockEntity entity,String sample) {
        JsonObject detail=block(world,pos,entity.getPushedBlock());
        float progress=((ObservationPistonAccess)entity).stonebench$progress();
        Direction facing=entity.getFacing();double offset=entity.isExtending()?progress-1:1-progress;
        BlockState moved=entity.getPushedBlock();
        if(entity.isSource()) moved=((ObservationPistonAccess)entity).stonebench$headBlockState();
        var shape=moved.getOutlineShape(world,pos);
        detail.addProperty("block",Registries.BLOCK.getId(moved.getBlock()).toString());
        if(!shape.isEmpty())detail.add("bounds",box(shape.getBoundingBox().offset(pos).offset(facing.getOffsetX()*offset,facing.getOffsetY()*offset,facing.getOffsetZ()*offset)));
        detail.addProperty("sample",sample);detail.addProperty("progress",progress);detail.addProperty("extending",entity.isExtending());detail.addProperty("source",entity.isSource());detail.addProperty("facing",facing.asString());
        detail.add("destination",Task.position(pos.getX(),pos.getY(),pos.getZ()));
        BlockPos origin=pos.offset(facing,entity.isExtending()?-1:1);detail.add("origin",Task.position(origin.getX(),origin.getY(),origin.getZ()));
        Observation.event(world,"piston_movement_sample",pos,detail);
    }
}

