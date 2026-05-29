Flow Cad Viewer

Our primary goal is to develop a viewer that will facility faster work with LLMs.
Out initial goal is not to create a full parametric CAD program.  It may evolve there over time, but that is not the initial design goal.

Requirements
read .step, .stl files and view, measure, edit them

Fast-api backend
React front end
rich-cli for cli

flow-cad start should start the server adn open browser window
flow-cad reload should reload whatever server is started.  See the /home/gnulnx/LlamaStudio code base for example of how simple and smooth the cli experience should be.

Main Features
First class rotations  I think we have this now, but text-to-cad is a good example of god rotations.  FreeCad is an example of awful rotations. 
Mouse  controlrs!
Left click and move is rotate.  !
Right click and move is translate
Middle wheel is zoom
control + right click object = translate/resize origin tool appears.

A tape measure tool.  I should be able to measure from any 2 points on the screen  if near an edge or vertice it should have a ‘snap’ to edge/vertice. I should also be able to draw out from an edge/vertice to another point on the model (or space) and have it show me the distance and drop a point.  For instance if I wanted a screw hole 45mm from an edge I should be able to select an edge draw out 45mm drop a point. The select the hole tool (coming up) and select hole type M4/M5/etc.. just start with those 2 for now and create a whole exact 45mm out.  It needs to be stupid simple.  then I simple select the point I dropped with tape measure tool and create the hole.
Basic Part Design:
Hole punch as discussed above we should have standard hole type. M4/M5, recessed M4/M5.  That is probably enough to start with.    Also through hole of heat set hole (mostly determined by the holes environhment
I should be ble to add and remove parts simply.  
Part addition is similar to FreeCad Part workbench. I can add a cube or sphere and right click the object to get a translate and resize from the same 3D tool.  This should function very much like FreeCads translate tool shown in image found in this directory

'Screenshot from 2026-05-29 06-46-53.png'

This would have 3 points of functionality.  A cube or sphere at the origin base.  A user can click and drag the entire part around with that.  Each axis should aloos the user to move the object on that axis alone.  Each axis will have to points.   A mid point they can use to drack along the same axis and an end arrow that they can use to extend/contract the length of the object.

Once the part is on the screen the users should be able to right click and position and resize this object very easily.  For now Lets focus ONLY on a cube tool until we get the functionality correct.

Once the part is aligned we should be able to fuse to parent by selecting both and then then a fuse menu button and that should live next tot he cut menu button. 

A user should be able to select a part and hit delete to remove it.. control z should restore it..

In general this tool should function more like plasticity  than free cad.  think rapid robot design tool vs lets create a new gear box assembly for now.


All parts should be showing in the viewer in assembled form. On the right side of the application there is a parts menu. a single click will show the a single part.  addition parts can be added by holding control and clicking.  this will let mem easily pull items inot the view in an assembled form and examine them> I have not need for non assembled parts in the view.

On teh left side of the view will be a python script interface.  WheN I an editing a part I should see the python code for that part. Likely wise if codex/llm is editing a part I should see that code in the left side panel.

Each part should already have it’s own python code wiht of course some shared code. I’m open to ideas on how we make the code fully transparent and editable from the app, but I want to see the code, but able to make quick mods and hit update and see my part change quickly..  This tool maybe ultimately be more useful working with llms than the actual part design tool.  If I can quickly edit a few params and move things around we can iterate much more rapidly




