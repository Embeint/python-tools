#!/usr/bin/env python3

"""Connect to remote Bluetooth device and render device based on accelerometer stream """

__author__ = "Aeyohan Furtado"
__copyright__ = "Copyright 2025, Embeint Inc"


import math
import os
import queue
import sys
import time
import threading
from infuse_iot.commands import InfuseCommand
from infuse_iot.common import InfuseType
from infuse_iot.epacket import interface
from infuse_iot.socket_comms import (
    ClientNotificationConnectionDropped,
    ClientNotificationEpacketReceived,
    GatewayRequestConnectionRequest,
    LocalClient,
    default_multicast_address,
)
from infuse_iot.tdf import TDF

import vtk

class SubCommand(InfuseCommand):
    NAME = "3d_acc"
    HELP = "Plot 3D acc data"
    DESCRIPTION = "Plot live accelerometer data in 3D"

    def __init__(self, args):
        self._client = LocalClient(default_multicast_address(), 1.0)
        self._decoder = TDF()
        self._id = args.id
        self.connected = False
        self.running = True
        self.roll = 0.0
        self.pitch = 0.0
        self.euler_sample = (0.0, 0.0)
        raw_lim = 0 #104 * 3
        self.raw_queue = queue.Queue(raw_lim)
        self.result_queue = queue.Queue(30)

        self.vtk_actors = None
        self.vtk_render_window = None

    def update_scene(self, _, __):
        if self.running is False:
            print("Stopping scene update, connection lost")
            self.vtk_render_window.Finalize()

            return
        self.vtk_actors.InitTraversal()
        vtk_next_actor = self.vtk_actors.GetNextActor()
        if self.result_queue.empty():
            # Repeat last sample if queue is empty
            sample = self.euler_sample
        else:
            sample = self.result_queue.get()
            self.euler_sample = sample
        roll, pitch = sample

        actor = 0
        while vtk_next_actor is not None:
            vtk_next_actor.SetOrientation(-90, 90, 0)
            vtk_next_actor.RotateX(roll)
            vtk_next_actor.RotateY(pitch)
            vtk_next_actor.SetScale(0.6, 0.6, 0.6)
            # vtk_next_actor.GetProperty().LightingOff()
            # colourScale = 1.5
            top = (0.17647058823529413, 0.2823529411764706, 0.35294117647058826)
            bottom = (0.8509803921568627, 0.34509803921568627, 0.29411764705882354)
            # top = tuple(x * colourScale for x in top)
            # bottom = tuple(x * colourScale for x in bottom)
            if (actor == 0):
                vtk_next_actor.GetProperty().SetColor(*top)
            else:
                vtk_next_actor.GetProperty().SetColor(*bottom)
            actor += 1
            vtk_next_actor = self.vtk_actors.GetNextActor()
        self.vtk_render_window.Render()

    def init_scene(self):
        print("Initializing 3D scene...")
        time.sleep(0.1)
        data  = os.path.join(os.path.dirname(__file__), "data", "Thingy53_Casing_Top.glb")
        data2 = os.path.join(os.path.dirname(__file__), "data", "Thingy53_Casing_Base.glb")
        print(f"Loading 3D model from {data}")
        importer = vtk.vtkGLTFImporter()
        importer.SetFileName(data)
        importer.Read()
        importer.SetFileName(data2)
        importer.Read()


        vtk.vtkButtonWidget()

        self.vtk_render_window
        vtk_renderer = importer.GetRenderer()
        self.vtk_render_window = importer.GetRenderWindow()
        vtk_render_window_interactor = vtk.vtkRenderWindowInteractor()
        vtk_render_window_interactor.SetRenderWindow(self.vtk_render_window)

        vtk_renderer.GradientBackgroundOn()
        vtk_renderer.SetBackground(0.2, 0.2, 0.2)
        vtk_renderer.SetBackground2(0.3, 0.3, 0.3)
        self.vtk_render_window.SetSize(600, 600)
        self.vtk_render_window.SetWindowName('Infuse: 3D Accelerometer Visualizer')

        vtk_render_window_interactor.Initialize()
        vtk_renderer.GetActiveCamera().Zoom(1.0)
        vtk_renderer.GetActiveCamera().SetRoll(90)
        vtk_renderer.GetActiveCamera().SetClippingRange(0.01, 100)
        vtk_renderer.GetActiveCamera().SetViewAngle(40)
        vtk_renderer.SetClippingRangeExpansion(0.1)  # Adjust so clipping of polygons doesn't show
        vtk_renderer.TwoSidedLightingOn()
        vtk_renderer.SetAmbient([1.5, 1.5, 1.5])
        vtk_renderer.ResetCamera()
        self.vtk_render_window.Render()
        print("3D scene initialized.")

        # Add data callback
        vtk_render_window_interactor.CreateRepeatingTimer(1)
        vtk_render_window_interactor.AddObserver("TimerEvent", self.update_scene)

        self.vtk_actors = vtk_renderer.GetActors()
        vtk_render_window_interactor.Start()

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--id", type=lambda x: int(x, 0), help="Infuse ID to receive logs for")

    def process_data(self):
        print("Processing accelerometer data...")
        skip = 1
        sample_rate = 104 / skip
        sample_period = 1 / sample_rate
        count = 0

        while self.running:
            if not self.raw_queue.empty():
                if (self.raw_queue.qsize() > sample_rate):
                    skip = 1 + (self.raw_queue.qsize() / sample_rate) / 10
                else:
                    skip = 1
                sample = self.raw_queue.get()
                count += 1
                if count % skip != 0:
                    count = 0
                    continue
                start = time.time()
                # print("Processing sample", self.raw_queue.qsize(), skip)
                # sample = point.sample
                
                x = sample.y
                y = -sample.x
                z = sample.z
                roll = math.atan2(y, ((x ** 2) + (z ** 2)) ** 0.5) * 180 / math.pi
                pitch = math.atan2(-1 * x, ((y ** 2) + (z ** 2)) ** 0.5) * 180 / math.pi

                # Goes upside down, but yaw is whacky and generally is unstable
                # x = sample.y
                # y = -sample.x
                # z = sample.z
                # roll = math.atan2(y, z) * 180 / math.pi
                # pitch = math.asin(x/ ((x ** 2) + (y ** 2) + (z ** 2)) ** 0.5) * 180 / math.pi

                # Goes upside down same as above.
                # x = sample.y
                # y = -sample.x
                # z = sample.z
                # sign = -1 if z < 0 else 1
                # roll = math.atan2(y, sign * ((x ** 2) + (z ** 2)) ** 0.5) * 180 / math.pi
                # pitch = math.atan2(-1 * x, ((y ** 2) + (z ** 2)) ** 0.5) * 180 / math.pi



                # fitler
                self.roll = 0.9 * self.roll + 0.1 * roll
                self.pitch = 0.9 * self.pitch + 0.1 * pitch
                end = time.time()
                delta = end - start
                # print(f"Processing time: {((delta) * 1E6):.3f} µs")
                # self.roll = roll
                # self.pitch = pitch

                sample = (self.roll, self.pitch)
                if not self.result_queue.full():
                    self.result_queue.put(sample)
                    time.sleep(sample_period)
                    # if skip > 1:
                    #     skip -= 1
                else:
                    # Drop data
                    print("Data queue full, dropping sample %d" % skip)
                    # skip += 1
            time.sleep(0.0001)

    def receive_data(self):
        try:
            types = GatewayRequestConnectionRequest.DataType.DATA
            cnt = 0
            thread = threading.Thread(target=self.process_data)
            thread.start()
            connected = False
            start = time.time()

            while self.running:
                with self._client.connection(self._id, types) as _:
                    connected = True
                    while evt := self._client.receive():
                        if evt is None:
                            continue
                        if isinstance(evt, ClientNotificationConnectionDropped):
                            print(f"Connection to {self._id:016x} lost")
                            connected = False
                            time.sleep(1)
                            break
                        if not isinstance(evt, ClientNotificationEpacketReceived):
                            continue
                        source = evt.epacket.route[0]
                        if source.infuse_id != self._id:
                            continue
                        if source.interface != interface.ID.BT_CENTRAL:
                            continue

                        if evt.epacket.ptype == InfuseType.TDF:
                            for tdf in self._decoder.decode(evt.epacket.payload):
                                if tdf.id in {10, 11, 12, 13}:
                                    self.connected = True
                                    # print(f"{len(tdf.data)} samples at {(time.time() - start):.3f} s")
                                    for point in tdf.data:
                                        # cnt += 1
                                        # if cnt % skip != 0:
                                        #     continue
                                        
                                        if (self.raw_queue.full()):
                                            print("Raw data queue full, dropping sample")
                                            continue
                                        self.raw_queue.put(point.sample)
                                        # time.sleep(0.0001)  # Small delay to allow rendering

                                        # print("Accelerometer", time.time(), tdf.time)
                                        # sample = point.sample
                                        # x = sample.x
                                        # y = sample.y
                                        # z = sample.z
                                        # roll = math.atan(y / ((x ** 2) + (z ** 2)) ** 0.5) * 180 / math.pi
                                        # pitch = math.atan(-1 * x / ((y ** 2) + (z ** 2)) ** 0.5) * 180 / math.pi

                                        # # fitler
                                        # self.roll = 0.9 * self.roll + 0.1 * roll
                                        # self.pitch = 0.9 * self.pitch + 0.1 * pitch
                                        # # self.roll = roll
                                        # # self.pitch = pitch

                                        # sample = (self.roll, self.pitch)
                                        # if not self.result_queue.full():
                                        #     self.result_queue.put(sample)
                                        #     time.sleep(sample_period)
                                        #     # if skip > 1:
                                        #     #     skip -= 1
                                        # else:
                                        #     # Drop data
                                        #     print("Data queue full, dropping sample %d" % skip)
                                        #     # skip += 1
                                        #     pass
                                        # Small delay to allow rendering
                                        # time.sleep(0.001)  # Small delay to allow rendering

                                # t = tdf.data[-1]
                                # t_str = f"{tdf.time:.3f}" if tdf.time else "N/A"
                                # if len(tdf.data) > 1:
                                #     print(f"{t_str} TDF: {t.NAME}[{len(tdf.data)}]")
                                # else:
                                #     print(f"{t_str} TDF: {t.NAME}")

        except KeyboardInterrupt:
            print(f"Disconnecting from {self._id:016x}")
        except ConnectionRefusedError:
            print(f"Unable to connect to {self._id:016x}")
        self.running = False
        if self.connected:
            pass

    def run(self):
        # Lauch receive_data in a separate thread
        data_thread = threading.Thread(target=self.receive_data)
        data_thread.start()

        # Wait for connection to be established before rendering
        # while not self.connected:
        #     time.sleep(0.1)
        self.init_scene()
        self.running = False
        time.sleep(0.1)  # Allow scene to initialize
        sys.exit(0)
        