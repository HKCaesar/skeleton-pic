#-----------------------------------------------------------------------
# Skeleton 2D Electrostatic MPI/OpenMP PIC code
# written by Viktor K. Decyk, UCLA
import math
import numpy
from cmppush2 import *
from dtimer import *
from complib import *

int_type = numpy.int32
double_type = numpy.float64
float_type = numpy.float32
complex_type = numpy.complex64

# indx/indy = exponent which determines grid points in x/y direction:
# nx = 2**indx, ny = 2**indy.
indx =   9; indy =   9
# npx/npy = number of electrons distributed in x/y direction.
npx =  3072; npy =   3072
# ndim = number of velocity coordinates = 2
ndim = 2
# tend = time at end of simulation, in units of plasma frequency.
# dt = time interval between successive calculations.
# qme = charge on electron, in units of e.
tend = 10.0; dt = 0.1; qme = -1.0
# vtx/vty = thermal velocity of electrons in x/y direction
# vx0/vy0 = drift velocity of electrons in x/y direction.
vtx = 1.0; vty = 1.0; vx0 = 0.0; vy0 = 0.0
# ax/ay = smoothed particle size in x/y direction
ax = .912871; ay = .912871
# idimp = dimension of phase space = 4
# ipbc = particle boundary condition: 1 = periodic
idimp = 4; ipbc = 1
# idps = number of partition boundaries
idps = 2
# wke/we/wt = particle kinetic/electric field/total energy
wke = numpy.zeros((1),float_type)
we = numpy.zeros((1),float_type)
wt = numpy.zeros((1),float_type)
# sorting tiles, should be less than or equal to 32
mx = 16; my = 16
# fraction of extra particles needed for particle management
xtras = 0.2

# declare scalars for MPI code
ntpose = 1
argv = numpy.empty((1),numpy.str)
nnvp = numpy.empty((1),int_type)
nidproc = numpy.empty((1),int_type)
nnyp = numpy.empty((1),int_type)
nnoff = numpy.empty((1),int_type)
nnpp = numpy.empty((1),int_type)
nnypmx = numpy.empty((1),int_type)
nnypmn = numpy.empty((1),int_type)
ierr = numpy.empty((1),int_type)

# declare scalars for OpenMP code
nppmx = numpy.empty((1),int_type)
irc = numpy.zeros((1),int_type)
nvpp = numpy.empty((1),int_type)

# declare and initialize timing data
itime = numpy.empty((4),numpy.int32)
tdpost = 0.0; tguard = 0.0; tfield = 0.0
tpush = 0.0; tsort = 0.0; tmov = 0.0
ttp = numpy.zeros((1),float_type)
tfft = numpy.zeros((2),float_type)
dtime = numpy.empty((1),double_type)

# nvpp = number of shared memory nodes (0=default)
nvpp = 0
#nvpp = int(input("enter number of nodes: "))
# initialize for shared memory parallel processing
cinit_omp(nvpp)

# initialize scalars for standard code
# np = total number of particles in simulation
np =  float(npx)*float(npy)
# nx/ny = number of grid points in x/y direction
nx = int(math.pow(2,indx)); ny = int(math.pow(2,indy))
nxh = int(nx/2); nyh = max(1,int(ny/2))
nxe = nx + 2; nye = ny + 2; nxeh = int(nxe/2); nnxe = ndim*nxe
nxyh = int(max(nx,ny)/2); nxhy = max(nxh,ny)
# mx1 = number of tiles in x direction
mx1 = int((nx - 1)/mx) + 1
# nloop = number of time steps in simulation
# ntime = current time step
nloop = int(tend/dt + .0001); ntime = 0
qbme = qme
affp = float(nx)*float(ny)/np
      
# nvp = number of distributed memory nodes
# initialize for distributed memory parallel processing
cppinit2(nidproc,nnvp,0,argv)
idproc = nidproc[0]; nvp = nnvp[0]
kstrt = idproc + 1
# check if too many processors
if (nvp > ny):
   if (kstrt==1):
      print "Too many processors requested: ny, nvp=", ny, nvp
   cppexit()
   exit(0)

# initialize data for MPI code
edges = numpy.empty((idps),float_type,'F')
# calculate partition variables: edges, nyp, noff, nypmx
# edges[0:1] = lower:upper boundary of particle partition
# nyp = number of primary (complete) gridpoints in particle partition
# noff = lowermost global gridpoint in particle partition
# nypmx = maximum size of particle partition, including guard cells
# nypmn = minimum value of nyp
cpdicomp2l(edges,nnyp,nnoff,nnypmx,nnypmn,ny,kstrt,nvp,idps)
nyp = nnyp[0]; noff = nnoff[0]; nypmx = nnypmx[0]; nypmn = nnypmn[0]
if (nypmn < 1):
   if (kstrt==1):
      print "combination not supported nvp, ny =",nvp,ny
   cppexit()
   exit(0)

# initialize additional scalars for MPI code
# kxp = number of complex grids in each field partition in x direction
kxp = int((nxh - 1)/nvp) + 1
# kyp = number of complex grids in each field partition in y direction
kyp = int((ny - 1)/nvp) + 1
# npmax = maximum number of electrons in each partition
npmax = int((np/float(nvp))*1.25)
# myp1 = number of tiles in y direction
myp1 = int((nyp - 1)/my) + 1; mxyp1 = mx1*myp1

# allocate data for standard code
# part = particle array
part = numpy.empty((idimp,npmax),float_type,'F')
# qe = electron charge density with guard cells
qe = numpy.empty((nxe,nypmx),float_type,'F')
# fxye = smoothed electric field with guard cells
fxye = numpy.empty((ndim,nxe,nypmx),float_type,'F')
# qt = scalar charge density field array in fourier space
qt = numpy.empty((nye,kxp),complex_type,'F')
# fxyt = vector electric field array in fourier space
fxyt = numpy.empty((ndim,nye,kxp),complex_type,'F')
# ffc = form factor array for poisson solver
ffc = numpy.empty((nyh,kxp),complex_type,'F')
# mixup = bit reverse table for FFT
mixup = numpy.empty((nxhy),int_type,'F')
# sct = sine/cosine table for FFT
sct = numpy.empty((nxyh),complex_type,'F')
# kpic = number of particles in each tile
kpic = numpy.empty((mxyp1),int_type,'F')
wtot = numpy.empty((4),double_type)
work = numpy.empty((4),double_type)

# allocate data for MPI code
# bs/br = complex send/receive buffers for data transpose
bs = numpy.empty((ndim,kxp,kyp),complex_type,'F')
br = numpy.empty((ndim,kxp,kyp),complex_type,'F')
# scs/scr = guard cell buffers received from nearby processors
scs = numpy.empty((ndim*nxe),float_type,'F')
scr = numpy.empty((ndim*nxe),float_type,'F')

# prepare fft tables
cwpfft2rinit(mixup,sct,indx,indy,nxhy,nxyh)
# calculate form factors
isign = 0
cmppois22(qt,fxyt,isign,ffc,ax,ay,affp,we,nx,ny,kstrt,nye,kxp,nyh)
# initialize electrons
nps = 1
nnpp[0] = 0
cpdistr2(part,edges,nnpp,nps,vtx,vty,vx0,vy0,npx,npy,nx,ny,idimp,npmax,
         idps,ipbc,ierr)
npp = nnpp[0]
# check for particle initialization error
if (ierr[0] != 0):
   if (kstrt==1):
      print "particle initialization error: ierr=", ierr[0]
   cppexit()
   exit(0)

# find number of particles in each of mx, my tiles: updates kpic, nppmx
cppdblkp2l(part,kpic,npp,noff,nppmx,idimp,npmax,mx,my,mx1,mxyp1,irc)
if (irc[0] != 0):
   print "ppdblkp2l error, irc=", irc[0]
   cppabort()
   exit(0)

# allocate vector particle data
nppmx0 = int((1.0 + xtras)*nppmx)
ntmaxp = int(xtras*nppmx)
npbmx = int(xtras*nppmx)
nbmaxp = int(0.25*mx1*npbmx)
# sbufl/sbufr = particle buffers sent to nearby processors
sbufl = numpy.empty((idimp,nbmaxp),float_type,'F')
sbufr = numpy.empty((idimp,nbmaxp),float_type,'F')
# rbufl/rbufr = particle buffers received from nearby processors
rbufl = numpy.empty((idimp,nbmaxp),float_type,'F')
rbufr = numpy.empty((idimp,nbmaxp),float_type,'F')
# ppart = tiled particle array
ppart = numpy.empty((idimp,nppmx0,mxyp1),float_type,'F')
# ppbuff = buffer array for reordering tiled particle array
ppbuff = numpy.empty((idimp,npbmx,mxyp1),float_type,'F')
# ncl = number of particles departing tile in each direction
ncl = numpy.empty((8,mxyp1),int_type,'F')
# iholep = location/destination of each particle departing tile
iholep = numpy.empty((2,ntmaxp+1,mxyp1),int_type,'F')
# ncll/nclr/mcll/mclr = number offsets send/received from processors
ncll = numpy.empty((3,mx1),int_type,'F')
nclr = numpy.empty((3,mx1),int_type,'F')
mcll = numpy.empty((3,mx1),int_type,'F')
mclr = numpy.empty((3,mx1),int_type,'F')

# copy ordered particle data for OpenMP
cpppmovin2l(part,ppart,kpic,npp,noff,nppmx0,idimp,npmax,mx,my,mx1,mxyp1,
            irc)
if (irc[0] != 0):
   print "pppmovin2l overflow error, irc=", irc[0]
   cppabort()
   exit(0)
# sanity check
cpppcheck2l(ppart,kpic,noff,nyp,idimp,nppmx0,nx,mx,my,mx1,myp1,irc)
if (irc[0] != 0):
   print "pppcheck2l error, irc=", irc[0]
   cppabort()
   exit(0)

# * * * start main iteration loop * * *

for ntime in xrange(0,nloop):
#  if (kstrt==1):
#     print "ntime = ", ntime

# deposit charge with OpenMP: updates qe
   dtimer(dtime,itime,-1)
   qe.fill(0.0)
   cppgppost2l(ppart,qe,kpic,noff,qme,idimp,nppmx0,mx,my,nxe,nypmx,mx1,
               mxyp1)
   dtimer(dtime,itime,1)
   time = float(dtime)
   tdpost = tdpost + time

# add guard cells with OpenMP: updates qe
   dtimer(dtime,itime,-1)
   cppaguard2xl(qe,nyp,nx,nxe,nypmx)
   cppnaguard2l(qe,scr,nyp,nx,kstrt,nvp,nxe,nypmx)
   dtimer(dtime,itime,1)
   time = float(dtime)
   tguard = tguard + time

# transform charge to fourier space with OpenMP: updates qt, modifies qe
   dtimer(dtime,itime,-1)
   isign = -1
   cwppfft2rm(qe,qt,bs,br,isign,ntpose,mixup,sct,ttp,indx,indy,kstrt,nvp,
              nxeh,nye,kxp,kyp,nypmx,nxhy,nxyh)
   dtimer(dtime,itime,1)
   time = float(dtime)
   tfft[0] = tfft[0] + time

# calculate force/charge in fourier space with OpenMP: updates fxyt, we
   dtimer(dtime,itime,-1)
   isign = -1
   cmppois22(qt,fxyt,isign,ffc,ax,ay,affp,we,nx,ny,kstrt,nye,kxp,nyh)
   dtimer(dtime,itime,1)
   time = float(dtime)
   tfield = tfield + time

# transform force to real space with OpenMP: updates fxye, modifies fxyt
   dtimer(dtime,itime,-1)
   isign = 1
   cwppfft2rm2(fxye,fxyt,bs,br,isign,ntpose,mixup,sct,ttp,indx,indy,
               kstrt,nvp,nxeh,nye,kxp,kyp,nypmx,nxhy,nxyh)
   dtimer(dtime,itime,1)
   time = float(dtime)
   tfft[0] = tfft[0] + time
   tfft[1] = tfft[1] + ttp[0]

# copy guard cells with OpenMP: updates fxye
   dtimer(dtime,itime,-1)
   cppncguard2l(fxye,nyp,kstrt,nvp,nnxe,nypmx)
   cppcguard2xl(fxye,nyp,nx,ndim,nxe,nypmx)
   dtimer(dtime,itime,1)
   time = float(dtime)
   tguard = tguard + time

# push particles with OpenMP:
   dtimer(dtime,itime,-1)
   wke[0] = 0.0
# updates ppart and wke
#  cppgppush2l(ppart,fxye,kpic,noff,nyp,qbme,dt,wke,nx,ny,mx,my,idimp,
#              nppmx0,nxe,nypmx,mx1,mxyp1,ipbc)
# updates ppart, wke, ncl, iholep, irc
   cppgppushf2l(ppart,fxye,kpic,ncl,iholep,noff,nyp,qbme,dt,wke,nx,ny,mx,
                my,idimp,nppmx0,nxe,nypmx,mx1,mxyp1,ntmaxp,irc)
   dtimer(dtime,itime,1)
   time = float(dtime)
   tpush = tpush + time
   if (irc[0] != 0):
      print "ppgppushf2l error, irc=", irc[0]
      cppabort()
      exit(0)

# reorder particles by tile with OpenMP
# first part of particle reorder on x and y cell with mx, my tiles:
   dtimer(dtime,itime,-1)
# updates ppart, ppbuff, sbufl, sbufr, ncl, iholep, ncll, nclr, irc
#  cppporder2la(ppart,ppbuff,sbufl,sbufr,kpic,ncl,iholep,ncll,nclr,noff,
#               nyp,idimp,nppmx0,nx,ny,mx,my,mx1,myp1,npbmx,ntmaxp,
#               nbmaxp,irc)
# updates ppart, ppbuff, sbufl, sbufr, ncl, ncll, nclr, irc
   cppporderf2la(ppart,ppbuff,sbufl,sbufr,ncl,iholep,ncll,nclr,idimp,
                 nppmx0,mx1,myp1,npbmx,ntmaxp,nbmaxp,irc)
   dtimer(dtime,itime,1)
   time = float(dtime)
   tsort = tsort + time
   if (irc[0] != 0):
      print kstrt, "ppporderf2la error: ntmaxp, irc=", ntmaxp, irc[0]
      cppabort()
      exit(0)
# move particles into appropriate spatial regions:
# updates rbufr, rbufl, mcll, mclr
   dtimer(dtime,itime,-1)
   cpppmove2(sbufr,sbufl,rbufr,rbufl,ncll,nclr,mcll,mclr,kstrt,nvp,idimp,
             nbmaxp,mx1)
   dtimer(dtime,itime,1)
   time = float(dtime)
   tmov = tmov + time
# second part of particle reorder on x and y cell with mx, my tiles:
# updates ppart, kpic
   dtimer(dtime,itime,-1)
   cppporder2lb(ppart,ppbuff,rbufl,rbufr,kpic,ncl,iholep,mcll,mclr,idimp,
                nppmx0,mx1,myp1,npbmx,ntmaxp,nbmaxp,irc)
   dtimer(dtime,itime,1)
   time = float(dtime)
   tsort = tsort + time
   if (irc[0] != 0):
      print kstrt, "ppporder2lb error: nppmx0, irc=", nppmx0, irc[0]
      cppabort()
      exit(0)

# energy diagnostic
   wtot[0] = we
   wtot[1] = wke[0]
   wtot[2] = 0.0
   wtot[3] = we[0] + wke[0]
   cppdsum(wtot,work,4)
   we[0] = wtot[0]
   if (ntime==0):
      if (kstrt==1):
         print "Initial Field, Kinetic and Total Energies:"
         print "%14.7e %14.7e %14.7e" % (we, wke, wke + we)
ntime = ntime + 1

# * * * end main iteration loop * * *

if (kstrt==1):
   print "ntime = ", ntime
   print "MPI nodes nvp = ", nvp
   print "Final Field, Kinetic and Total Energies:"
   print "%14.7e %14.7e %14.7e" % (we, wke, wke + we)

   print ""
   print "deposit time = ", tdpost
   print "guard time = ", tguard
   print "solver time = ", tfield
   print "fft and transpose time = ", tfft[0], tfft[1]
   print "push time = ", tpush
   print "particle move time = ", tmov
   print "sort time = ", tsort
   tfield = tfield + tguard + tfft[0]
   print "total solver time = ", tfield
   tsort = tsort + tmov
   time = tdpost + tpush + tsort
   print "total particle time = ", time
   wt = time + tfield
   print "total time = ", wt
   print ""

   wt = 1.0e+09/(float(nloop)*float(np))
   print "Push Time (nsec) = ", tpush*wt
   print "Deposit Time (nsec) = ", tdpost*wt
   print "Sort Time (nsec) = ", tsort*wt
   print "Total Particle Time (nsec) = ", time*wt

cppexit()
